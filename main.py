import json
import pandas as pd
from typing import Dict, Any, List, Union
import google.generativeai as genai
import requests
import tempfile
import os
from urllib.parse import urlparse
import mimetypes

from typing import Dict, Optional
from google.cloud import bigquery
from google.oauth2 import service_account

from dotenv import load_dotenv
from cache_manager import CacheManager, VenueCache, GeminiCache

# ------------------------------------------------------------
# 関数: ip address
# ------------------------------------------------------------

def get_geo_info(ip: str) -> Dict[str, str]:
    """
    Get geolocation using ip-api.com (Free, no API key required)
    Rate limit: 45 requests per minute
    """
    try:
        url = f"http://ip-api.com/json/{ip}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        
        data = response.json()
        
        if data.get('status') == 'success':
            return {
                'country': data.get('country', ''),
                'countryCode': data.get('countryCode', ''),
                'regionName': data.get('regionName', ''),
                'city': data.get('city', ''),
                'zip': data.get('zip', ''),
                'lat': data.get('lat', ''),
                'lon': data.get('lon', ''),
                'timezone': data.get('timezone', ''),
                'isp': data.get('isp', ''),
                'org': data.get('org', ''),
                'as': data.get('as', ''),
                'query': data.get('query', '')
            }
        else:
            print(f"❌ ip-api.com error: {data.get('message', 'Unknown error')}")
            return {}
            
    except Exception as e:
        print(f"❌ ip-api.com request failed: {e}")
        return {}

# ------------------------------------------------------------
# 関数: gemini
# ------------------------------------------------------------

def download_image_from_url(url: str) -> str:
    """
    Download image from URL and save to temporary file
    
    Args:
        url (str): Image URL
        
    Returns:
        str: Path to downloaded temporary file
    """
    try:
        print(f"📥 Downloading image from: {url}")
        
        # Set headers to mimic a browser request
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Download the image
        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()
        
        # Determine file extension
        content_type = response.headers.get('content-type', '')
        if content_type.startswith('image/'):
            extension = mimetypes.guess_extension(content_type) or '.jpg'
        else:
            # Try to get extension from URL
            parsed_url = urlparse(url)
            path = parsed_url.path
            extension = os.path.splitext(path)[1] or '.jpg'
        
        # Create temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=extension) as temp_file:
            temp_file.write(response.content)
            temp_path = temp_file.name
        
        print(f"✅ Image downloaded successfully: {temp_path}")
        return temp_path
        
    except Exception as e:
        raise Exception(f"Failed to download image from URL: {str(e)}")

def analyze_event_flyer_flexible(image_source: Union[str, object], api_key: str, gemini_cache: GeminiCache = None) -> pd.DataFrame:
    """
    Analyzes an event flyer image from file path or URL using Google Gemini AI.
    
    Args:
        image_source (Union[str, object]): File path, URL, or uploaded file object
        api_key (str): Google API key
        
    Returns:
        pd.DataFrame: DataFrame with columns [date, event_name, venue, location] for each event
    """
    if not api_key:
        print("❌ API key is not provided")
        return pd.DataFrame(columns=["date", "event_name", "venue", "location"])

    temp_file_path = None
    
    # キャッシュチェック
    if gemini_cache and isinstance(image_source, str):
        cached_result = gemini_cache.get_analysis_result(image_source)
        if cached_result:
            print(f"🔄 Using cached Gemini analysis for: {image_source}")
            # キャッシュされた結果をDataFrameに変換
            if cached_result.get('events'):
                events_data = []
                for event in cached_result['events']:
                    event_data = {
                        "date": event.get("date"),
                        "event_name": event.get("event_name"), 
                        "venue": event.get("venue"),
                        "location": event.get("location")
                    }
                    events_data.append(event_data)
                
                df_result = pd.DataFrame(events_data)
                df_result = clean_event_data(df_result)
                return df_result
            else:
                return pd.DataFrame(columns=["date", "event_name", "venue", "location"])
    
    try:
        # Configure Gemini API
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        # Handle different input types
        if isinstance(image_source, str):
            if image_source.startswith(('http://', 'https://')):
                # URL case - download first
                temp_file_path = download_image_from_url(image_source)
                uploaded_file = genai.upload_file(temp_file_path)
                print(f"🖼️ Processing image from URL: {image_source}")
            else:
                # File path case
                uploaded_file = genai.upload_file(image_source)
                print(f"🖼️ Processing image from file: {image_source}")
        else:
            # Assume it's already an uploaded file object
            uploaded_file = image_source
            print("🖼️ Processing uploaded file object")

        # Improved prompt for multiple events
        prompt = """
        Analyze this event flyer image and extract information about ALL events shown.
        
        For EACH individual event, identify:
        1. Event name/title
        2. Date (in YYYY-MM-DD format)
        3. Venue name
        4. Location (city, address, or area)
        
        **Important Instructions:**
        - If multiple events are shown, create separate entries for each event
        - Match each event name with its corresponding date, venue, and location
        - If an event spans multiple dates, create separate entries for each date
        - If information is missing for an event, use null for that field
        - Be precise about which information belongs to which event
        - Look for DJ names, artist names, party names as event names
        - Look for club names, venue names, hall names, building name as venues
        
        Respond in this JSON format:
        {
            "is_event_flyer": true/false,
            "confidence": 0.0-1.0,
            "events": [
                {
                    "event_name": "Event Name 1",
                    "date": "2024-01-01",
                    "venue": "Venue Name 1", 
                    "location": "Location 1"
                },
                {
                    "event_name": "Event Name 2",
                    "date": "2024-01-02",
                    "venue": "Venue Name 2",
                    "location": "Location 2"
                }
            ]
        }
        
        If it's not an event flyer, set is_event_flyer to false and events to empty array.
        Extract information as accurately as possible and ensure each event has complete information.
        """

        # Generate content
        response = model.generate_content([uploaded_file, prompt])

        # Parse the JSON response
        try:
            # Clean the response text to extract JSON
            response_text = response.text
            if "```json" in response_text:
                json_start = response_text.find("```json") + 7
                json_end = response_text.find("```", json_start)
                response_text = response_text[json_start:json_end].strip()
            elif "```" in response_text:
                json_start = response_text.find("```") + 3
                json_end = response_text.rfind("```")
                response_text = response_text[json_start:json_end].strip()

            result = json.loads(response_text)
            
            # Debug output
            print(f"🔍 Analysis result: is_event_flyer={result.get('is_event_flyer')}, confidence={result.get('confidence')}")
            
            # Check if it's an event flyer
            if not result.get('is_event_flyer', False):
                print("⚠️ Image is not identified as an event flyer")
                return pd.DataFrame(columns=["date", "event_name", "venue", "location"])

            # Extract events
            events = result.get('events', [])
            
            if not events:
                print("⚠️ No events found in the flyer")
                return pd.DataFrame(columns=["date", "event_name", "venue", "location"])

            # Convert to DataFrame
            events_data = []
            for i, event in enumerate(events):
                event_data = {
                    "date": event.get("date"),
                    "event_name": event.get("event_name"), 
                    "venue": event.get("venue"),
                    "location": event.get("location")
                }
                events_data.append(event_data)
                print(f"📅 Event {i+1}: {event_data}")

            df_result = pd.DataFrame(events_data)
            
            # Clean up the data
            df_result = clean_event_data(df_result)
            
            # 結果をキャッシュに保存
            if gemini_cache and isinstance(image_source, str):
                cache_data = {
                    "is_event_flyer": result.get('is_event_flyer'),
                    "confidence": result.get('confidence'),
                    "events": result.get('events', [])
                }
                gemini_cache.set_analysis_result(image_source, cache_data)
            
            print(f"✅ Successfully extracted {len(df_result)} events")
            return df_result

        except json.JSONDecodeError as e:
            print(f"❌ JSON parse error: {str(e)}")
            print(f"Raw response: {response.text}")
            
            # Fallback: try to extract using the old format
            return fallback_extraction(response.text)

    except Exception as e:
        print(f"❌ Gemini API analysis failed: {str(e)}")
        return pd.DataFrame(columns=["date", "event_name", "venue", "location"])
    
    finally:
        # Clean up temporary file if created
        if temp_file_path and os.path.exists(temp_file_path):
            try:
                os.unlink(temp_file_path)
                print(f"🗑️ Cleaned up temporary file: {temp_file_path}")
            except:
                pass

def clean_event_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and validate the extracted event data
    """
    if len(df) == 0:
        return df
        
    # Remove rows where all essential fields are null
    essential_cols = ['date', 'event_name', 'venue']
    df_cleaned = df.dropna(subset=essential_cols, how='all')
    
    # Validate and clean dates
    df_cleaned['date'] = df_cleaned['date'].apply(validate_date)
    
    # Remove empty strings and replace with None
    for col in df_cleaned.columns:
        df_cleaned[col] = df_cleaned[col].apply(lambda x: None if x == "" or x == "null" else x)
    
    return df_cleaned.reset_index(drop=True)

def validate_date(date_str):
    """
    Validate and standardize date format
    """
    if pd.isna(date_str) or not date_str:
        return None
        
    # Try to parse and reformat the date
    try:
        import datetime
        # Handle various date formats
        for fmt in ['%Y-%m-%d', '%Y/%m/%d', '%m/%d/%Y', '%d/%m/%Y']:
            try:
                parsed_date = datetime.datetime.strptime(str(date_str), fmt)
                return parsed_date.strftime('%Y-%m-%d')
            except:
                continue
        return date_str  # Return original if no format matches
    except:
        return date_str

def fallback_extraction(response_text: str) -> pd.DataFrame:
    """
    Fallback extraction when JSON parsing fails
    """
    try:
        print("🔄 Attempting fallback extraction...")
        
        # Try to find lists in the response
        import re
        
        # Look for potential event names, dates, venues
        event_names = re.findall(r'"event_names?":\s*\[(.*?)\]', response_text, re.IGNORECASE)
        dates = re.findall(r'"dates?":\s*\[(.*?)\]', response_text, re.IGNORECASE)
        venues = re.findall(r'"venues?":\s*\[(.*?)\]', response_text, re.IGNORECASE)
        locations = re.findall(r'"locations?":\s*\[(.*?)\]', response_text, re.IGNORECASE)
        
        if event_names and dates:
            # Parse the lists
            event_list = [item.strip('"').strip() for item in event_names[0].split(',')]
            date_list = [item.strip('"').strip() for item in dates[0].split(',')]
            venue_list = [item.strip('"').strip() for item in venues[0].split(',')] if venues else []
            location_list = [item.strip('"').strip() for item in locations[0].split(',')] if locations else []
            
            # Create DataFrame with proper alignment
            max_length = max(len(date_list), len(event_list))
            
            events_data = []
            for i in range(max_length):
                events_data.append({
                    "date": date_list[i] if i < len(date_list) else None,
                    "event_name": event_list[i] if i < len(event_list) else None,
                    "venue": venue_list[i] if i < len(venue_list) else None,
                    "location": location_list[i] if i < len(location_list) else None
                })
            
            return pd.DataFrame(events_data)
            
    except Exception as e:
        print(f"❌ Fallback extraction failed: {e}")
    
    return pd.DataFrame(columns=["date", "event_name", "venue", "location"])

def process_flyer_improved(image_source: Union[str, object], api_key: str, gemini_cache: GeminiCache = None) -> pd.DataFrame:
    """
    Main function to process a flyer image from file path or URL
    
    Args:
        image_source: File path, URL, or uploaded file object
        api_key: Google API key
    """
    if isinstance(image_source, str) and image_source.startswith(('http://', 'https://')):
        print(f"🌐 Processing flyer from URL: {image_source}")
    elif isinstance(image_source, str):
        print(f"📁 Processing flyer from file: {image_source}")
    else:
        print("🖼️ Processing uploaded flyer object")
    
    # Analyze the flyer
    df_events = analyze_event_flyer_flexible(image_source, api_key, gemini_cache)
    
    if len(df_events) == 0:
        print("⚠️ No events extracted from the flyer")
        return df_events
    
    # Display results
    print(f"\n📋 Extracted {len(df_events)} events:")
    print("=" * 80)
    for idx, row in df_events.iterrows():
        print(f"Event {idx + 1}:")
        print(f"  📅 Date: {row['date']}")
        print(f"  🎵 Event: {row['event_name']}")
        print(f"  🏢 Venue: {row['venue']}")
        print(f"  📍 Location: {row['location']}")
        print("-" * 40)
    
    return df_events

# ------------------------------------------------------------
# 関数: places API & Bigquery
# ------------------------------------------------------------

def call_text_search_api(venue: str, location: str, api_key: str, venue_cache: VenueCache = None) -> Optional[Dict]:
    """
    Text Search API - place_idとdisplay_nameのみ取得
    """
    # キャッシュチェック
    if venue_cache:
        cached_result = venue_cache.get_places_api_result(venue, location)
        if cached_result:
            return cached_result
    
    url = "https://places.googleapis.com/v1/places:searchText"
    payload = {"textQuery": f"{venue} {location}"}
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.id,places.displayName",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        if "places" in data and data["places"]:
            p = data["places"][0]
            result = {
                "textsearch_place_id": p.get("id"),
                "textsearch_display_name": p.get("displayName", {}).get("text")
            }
            
            # 結果をキャッシュに保存
            if venue_cache:
                venue_cache.set_places_api_result(venue, location, result)
            
            return result
        
        # 結果なしの場合もキャッシュ（短時間）
        if venue_cache:
            venue_cache.set_places_api_result(venue, location, None, ttl=300)  # 5分間
        
        return None
        
    except Exception as e:
        print(f"❌ Text Search failed: {e}")
        return None

def get_venue_from_bigquery(place_id: str, venue_cache: VenueCache = None) -> Optional[Dict]:
    """
    BigQueryのvenuesテーブルからplace_idでデータを検索
    """
    # キャッシュチェック
    if venue_cache:
        cached_result = venue_cache.get_venue_detail(place_id)
        if cached_result:
            print(f"🔄 Using cached BigQuery result for: {place_id}")
            return cached_result
    
    try:
        query = f"""
        SELECT 
            place_id,
            display_name,
            formatted_address,
            business_status,
            types,
            latitude,
            longitude,
            country,
            administrative_area_level_1,
            locality
        FROM `{project_id}.{dataset_id}.{table_id}`
        WHERE place_id = @place_id
        LIMIT 1
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("place_id", "STRING", place_id)
            ]
        )
        
        query_job = bq_client.query(query, job_config=job_config)
        results = query_job.result()
        
        for row in results:
            print(f"✅ Found in BigQuery: {place_id}")
            result = {
                "detailapi_place_id": row.place_id,
                "detailapi_display_name": row.display_name,
                "detailapi_formatted_address": row.formatted_address,
                "detailapi_business_status": row.business_status,
                "detailapi_types": json.loads(row.types) if row.types else [],
                "detailapi_latitude": float(row.latitude) if row.latitude else None,
                "detailapi_longitude": float(row.longitude) if row.longitude else None,
                "detailapi_country": row.country,
                "detailapi_administrative_area_level_1": row.administrative_area_level_1,
                "detailapi_locality": row.locality
            }
            
            # 結果をキャッシュに保存
            if venue_cache:
                venue_cache.set_venue_detail(place_id, result)
            
            return result
        
        print(f"⚠️ Not found in BigQuery: {place_id}")
        return None
        
    except Exception as e:
        print(f"❌ BigQuery search failed: {e}")
        return None

def call_detail_api(place_id: str, api_key: str) -> Optional[Dict]:
    """
    Detail API - 9つのフィールド取得（display_name追加）
    """
    url = f"https://places.googleapis.com/v1/places/{place_id}"
    headers = {
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "displayName,formattedAddress,businessStatus,location,types,addressComponents",
        "Accept-Language": "en-US,en;q=0.9"
    }

    try:
        resp = requests.get(url, headers=headers, timeout=10)
        resp.raise_for_status()
        
        if resp.status_code == 200:
            data = resp.json()
            
            # Address componentsから国・都道府県・市区町村を抽出
            address_components = data.get('addressComponents', [])
            country = None
            administrative_area_level_1 = None
            locality = None
            
            for component in address_components:
                types = component.get("types", [])
                short_text = component.get("shortText", "")
                
                if "country" in types:
                    country = short_text
                elif "administrative_area_level_1" in types:
                    administrative_area_level_1 = short_text
                elif "locality" in types:
                    locality = short_text

            print(f"✅ Detail API retrieved: {place_id}")
            return {
                "detailapi_place_id": place_id,
                "detailapi_display_name": data.get('displayName', {}).get('text'),
                "detailapi_formatted_address": data.get('formattedAddress'),
                "detailapi_business_status": data.get('businessStatus'),
                "detailapi_types": data.get('types', []),
                "detailapi_latitude": data.get('location', {}).get('latitude'),
                "detailapi_longitude": data.get('location', {}).get('longitude'),
                "detailapi_country": country,
                "detailapi_administrative_area_level_1": administrative_area_level_1,
                "detailapi_locality": locality
            }
        return None

    except Exception as e:
        print(f"❌ Detail API failed: {e}")
        return None

def save_venue_to_bigquery(place_id: str, venue_data: Dict):
    """
    新しい会場データをBigQueryに保存（display_name追加）
    """
    try:
        # typesをJSON文字列に変換
        types_json = json.dumps(venue_data.get('detailapi_types', []))
        
        insert_query = f"""
        INSERT INTO `{project_id}.{dataset_id}.{table_id}` 
        (place_id, display_name, formatted_address, business_status, types, latitude, longitude, 
         country, administrative_area_level_1, locality)
        VALUES 
        (@place_id, @display_name, @formatted_address, @business_status, @types, @latitude, @longitude,
         @country, @administrative_area_level_1, @locality)
        """
        
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter("place_id", "STRING", place_id),
                bigquery.ScalarQueryParameter("display_name", "STRING", venue_data.get('detailapi_display_name')),
                bigquery.ScalarQueryParameter("formatted_address", "STRING", venue_data.get('detailapi_formatted_address')),
                bigquery.ScalarQueryParameter("business_status", "STRING", venue_data.get('detailapi_business_status')),
                bigquery.ScalarQueryParameter("types", "STRING", types_json),
                bigquery.ScalarQueryParameter("latitude", "FLOAT", venue_data.get('detailapi_latitude')),
                bigquery.ScalarQueryParameter("longitude", "FLOAT", venue_data.get('detailapi_longitude')),
                bigquery.ScalarQueryParameter("country", "STRING", venue_data.get('detailapi_country')),
                bigquery.ScalarQueryParameter("administrative_area_level_1", "STRING", venue_data.get('detailapi_administrative_area_level_1')),
                bigquery.ScalarQueryParameter("locality", "STRING", venue_data.get('detailapi_locality'))
            ]
        )
        
        query_job = bq_client.query(insert_query, job_config=job_config)
        query_job.result()
        
        print(f"✅ Saved to BigQuery: {place_id}")
        
    except Exception as e:
        print(f"❌ Failed to save to BigQuery: {e}")

def get_venue_details(place_id: str, api_key: str, venue_cache: VenueCache = None) -> Optional[Dict]:
    """
    会場詳細取得: BigQuery優先、なければDetail API
    """
    # Step 1: BigQueryから検索
    bq_result = get_venue_from_bigquery(place_id, venue_cache)
    
    if bq_result:
        return bq_result
    
    # Step 2: BigQueryにない場合はDetail API
    print(f"🔍 Calling Detail API for: {place_id}")
    detail_result = call_detail_api(place_id, api_key)
    
    if detail_result:
        # Detail APIで取得したデータをBigQueryに保存
        save_venue_to_bigquery(place_id, detail_result)
        
        # キャッシュにも保存
        if venue_cache:
            venue_cache.set_venue_detail(place_id, detail_result)
        
        return detail_result
    
    return None

def process_events_with_bigquery(df_events, api_key: str, venue_cache: VenueCache = None):
    """
    df_eventsの各行を処理（BigQuery優先）
    """
    print(f"🚀 Processing {len(df_events)} events (BigQuery first)")
    
    results = []
    
    for idx, row in df_events.iterrows():
        print(f"\n📍 Event {idx + 1}: {row.get('event_name', 'Unknown')}")
        
        venue = row.get('venue')
        location = row.get('location', '')
        
        if venue:
            print(f"🔍 Searching: {venue} {location}")
            
            # Step 1: Text Search
            text_result = call_text_search_api(venue, location, api_key, venue_cache)
            
            if text_result:
                print(f"✅ Found by text search: {text_result['textsearch_display_name']}")
                
                # Step 2: BigQuery優先でDetail取得
                place_id = text_result['textsearch_place_id']
                detail_result = get_venue_details(place_id, api_key, venue_cache)
                
                if detail_result:
                    # Text SearchとDetailの結果をマージ
                    combined_result = {**text_result, **detail_result}
                    results.append(combined_result)
                    print(f"✅ Detail: {detail_result['detailapi_country']}, {detail_result['detailapi_administrative_area_level_1']}, {detail_result['detailapi_locality']}")
                else:
                    results.append(text_result)
                    print("⚠️ Detail retrieval failed")
            else:
                results.append({})
                print("⚠️ Venue not found")
        else:
            results.append({})
            print("⚠️ No venue name")
        
        # Rate limiting
        import time
        time.sleep(0.1)
    
    return results

def add_api_data_to_df(df_events, api_results):
    """
    df_eventsにAPIデータを追加
    """
    df_result = df_events.copy()
    
    # 全APIフィールドを初期化
    api_columns = [
        'textsearch_place_id',
        'textsearch_display_name',
        'detailapi_place_id',
        'detailapi_display_name',
        'detailapi_formatted_address',
        'detailapi_business_status',
        'detailapi_types',
        'detailapi_latitude',
        'detailapi_longitude',
        'detailapi_country',
        'detailapi_administrative_area_level_1',
        'detailapi_locality'
    ]
    
    for col in api_columns:
        df_result[col] = None
    
    # データを追加
    for i, api_result in enumerate(api_results):
        if i < len(df_result):
            for field, value in api_result.items():
                if field in api_columns:
                    # typesはJSON文字列に変換（BigQueryから来た場合は既にlist）
                    if field == 'detailapi_types':
                        if isinstance(value, list):
                            df_result.loc[i, field] = json.dumps(value) if value else None
                        else:
                            df_result.loc[i, field] = value
                    else:
                        df_result.loc[i, field] = value
    
    return df_result

# ------------------------------------------------------------
# Usage Examples
# ------------------------------------------------------------

if __name__ == "__main__":
    # ------------------------------------------------------------
    # BigQuery & Google API 設定
    # ------------------------------------------------------------
    project_id = "linkflyer-469112"
    dataset_id = "linkflyer_api"
    table_id = "venues"

    credentials = service_account.Credentials.from_service_account_file(
        "/Users/nf/dev/Python/linkflyer_api/credential/linkflyer-469112-5e52e7c54be1.json"
    )

    bq_client = bigquery.Client(credentials=credentials, project=project_id)

    # Load environment variables from .env.local file
    env_path = os.path.join(os.path.dirname(__file__), '.env.local')
    load_dotenv(env_path)
    api_key = os.getenv("NEXT_PUBLIC_GOOGLE_API_KEY")
    
    # ------------------------------------------------------------
    # キャッシュ初期化
    # ------------------------------------------------------------
    cache_manager = CacheManager("cache", default_ttl=3600)  # 1時間のデフォルトTTL
    venue_cache = VenueCache(cache_manager)
    gemini_cache = GeminiCache(cache_manager)
    
    print(f"🔧 Cache initialized. Stats: {cache_manager.get_stats()}")
    
    # 期限切れキャッシュをクリーンアップ
    cache_manager.clear_expired()

    # ------------------------------------------------------------
    # 入力
    # ------------------------------------------------------------
    # File path example
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/iori_asano-17896936272255687.jpg"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/iori_asano-17970029807876995.jpg"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/satoshi_tomiie_multivenues.png"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/mujuryoku.png"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/iori_asano-17885859204203484.jpg"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/vent_kim.png"
    # img = "/Users/nf/dev/Python/linkflyer_api/assets/secondhandrecords.png"
    img = "/Users/nf/dev/Python/linkflyer_api/assets/lebain.png"

    
    # URL example
    # img = "https://clubberia.com/image/event/306240/3/1/306240.jpeg"
    # img = "https://clubberia.com/image/event/306335/1/1/306335.jpeg"
    # img = "https://imgproxy.ra.co/_/quality:66/w:1442/rt:fill/aHR0cHM6Ly9pbWFnZXMucmEuY28vNGUwOGRkMTk0YTUzZTNmMmVjMWU1MzlhNTM5NWNlZDI0NmNiMGUxNy5qcGc="
    # img = "https://circus-tokyo.jp/wp-content/uploads/2025/08/20250821.png"
    # img = "http://www.goodroombk.com/dev/wp-content/uploads/2025/07/Aug22-web.jpg"
    
    
    ip = "63.116.61.253" #"60.65.238.71" # "123.192.101.168" 

    # ------------------------------------------------------------
    # データ取得 / gemini
    # ------------------------------------------------------------

    # Process flyer from URL
    df_events = process_flyer_improved(img, api_key, gemini_cache)
    print(df_events)

    # ------------------------------------------------------------
    # データ取得 / ip address
    # ------------------------------------------------------------
    # Get geo info from IP
    geo_info = get_geo_info(ip)
    ip_country = geo_info['country']
    ip_region = geo_info['regionName']
    ip_city = geo_info['city']

    # ------------------------------------------------------------
    # Fill missing venue and location data
    # ------------------------------------------------------------
    df_events["venue"] = df_events["venue"].fillna(df_events["event_name"])
    df_events['location'] = df_events['location'].fillna(ip_country)
    
    # print("\n📊 Final processed events:")
    # print(df_events)

    # print("\n","=" * 80)
    # print('ip address / geo info:')
    # print(geo_info)

    # ------------------------------------------------------------
    # places API
    # ------------------------------------------------------------
    # print("📋 Processing Events with BigQuery Priority")
    # print("=" * 50)
    
    # API処理（BigQuery優先）
    api_results = process_events_with_bigquery(df_events, api_key, venue_cache)
    
    # DataFrameに追加
    df_final = add_api_data_to_df(df_events, api_results)
    
    # print(f"\n✅ Complete! Shape: {df_final.shape}")
    
    # 結果確認
    # print("\n📊 Final Columns:")
    # print("🔹 Original:", [col for col in df_final.columns if not col.startswith(('textsearch_', 'detailapi_'))])
    # print("🔹 Text Search:", [col for col in df_final.columns if col.startswith('textsearch_')])
    # print("🔹 Detail API:", [col for col in df_final.columns if col.startswith('detailapi_')])
    
    # サンプル表示
    # print(f"\n📄 Sample:")
    # display_cols = ['event_name', 'venue', 'textsearch_display_name', 'detailapi_country', 'detailapi_administrative_area_level_1']
    # available_cols = [col for col in display_cols if col in df_final.columns]
    # if available_cols:
    #     print(df_final[available_cols].head())
    
    print(df_final[['date', 'venue', 'textsearch_place_id', 'textsearch_display_name', 'detailapi_country','detailapi_administrative_area_level_1','detailapi_locality']].rename(columns={"detailapi_country":"country","detailapi_administrative_area_level_1":"region","detailapi_locality":"city"}))

