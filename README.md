# linkflyer_api

----------------------------------------------
## 環境構築
----------------------------------------------
```bash
# Python rootディレクトリ内で以下を実行
python -m venv .venv # 仮想環境の作成
source .venv/bin/activate # アクティブ化

# requirements.txtをインストール（必要なら）
pip install -r requirements.txt

# requirements.txtを更新
pip freeze > requirements.txt 

```

----------------------------------------------
## flyer解析とvenue検索の精度向上について
----------------------------------------------
flyer解析とvenue検索の精度向上について、いくつかの改善提案があります。
現在の問題点

Gemini解析の精度: venue_nameとlocationの抽出が不安定
BigQuery検索の限界: ファジーマッチングが単純すぎる
検索戦略: 単一の検索手法に依存

改善提案
1. Gemini解析の改善改善されたGemini解析プロンプトCode def analyze_event_flyer_improved(image_path: str) -> Dict[str, Any]:
    """
    改善されたフライヤー解析（より構造化されたプロンプト）
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        uploaded2. 検索システムの改善
BigQueryだけでなく、専用の検索エンジンを組み合わせることをお勧めします：改善された会場検索システムCode from fuzzywuzzy import fuzz, process
import re
from typing import List, Tuple, Optional
import unicodedata

class VenueSearchEngine:
    def __init__(self, bq_client, project_id, dataset_id, table_id):
        self.bq_client = bq_client
        self.3. 検索システムのアーキテクチャ推奨検索システムアーキテクチャDocument # 会場検索システム アーキテクチャ提案

## 現在の課題

1. **BigQueryの限界**
   - ファジーマッチングが基本的
   - 全文検索機能が限定的
   - リアルタイム検索に不向き

2. **検索精度の問題**
   - 表記揺れに対応できない
   - 部分一致の優先順位が不適切
   - 地理的情報を活用できていない

## 推奨アーキテクチャ

### レベル1: BigQuery + 改善されたロジック（短期）

```
Gemini解析 → 改善された検索ロまとめ
短期的には、BigQueryベースのシステムを改善することをお勧めします：

Geminiプロンプトの構造化でextraction精度を向上
複数検索戦略の組み合わせでマッチング精度を向上
キャッシュ機能でパフォーマンス改善

中長期的には、Elasticsearch/OpenSearchの導入を検討してください：

全文検索とベクトル検索の組み合わせ
地理的検索の活用
継続的な学習機能

現在のコードベースなら、まず提案したVenueSearchEngineクラスを導入することで、大幅な改善が期待できます。BigQueryを完全に置き換える必要はなく、検索ロジックの改善から始めることをお勧めします。

----------------------------------------------
### 1. Gemini解析の改善
----------------------------------------------
```python
def analyze_event_flyer_improved(image_path: str) -> Dict[str, Any]:
    """
    改善されたフライヤー解析（より構造化されたプロンプト）
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        
        uploaded_file = genai.upload_file(image_path)
        
        # より詳細で構造化されたプロンプト
        prompt = """
        このイメージがイベントフライヤーかどうかを判定し、以下の情報を抽出してください：

        **抽出ルール:**
        1. **会場名 (venues)**: 
           - ライブハウス、クラブ、ホール、劇場などの施設名
           - 「@」「at」「会場:」などの後に続く文字列
           - 住所や地名ではなく、施設の固有名詞を優先
           
        2. **イベント名 (event_names)**:
           - パーティー名、コンサート名、イベントタイトル
           - DJセット名やアーティスト名も含む
           
        3. **日付 (dates)**:
           - YYYY-MM-DD形式で出力
           - 曜日や時間情報は除外
           
        4. **所在地 (location)**:
           - 都市名、区名、駅名など地理的な場所
           - 住所の一部でも可
           
        **出力形式:**
        ```json
        {
            "is_event_flyer": true/false,
            "confidence": 0.0-1.0,
            "event_names": ["イベント名1", "イベント名2"],
            "dates": ["2024-01-01", "2024-01-02"], 
            "venues": ["会場名1", "会場名2"],
            "location": ["渋谷", "新宿"],
            "extracted_text": "フライヤーから読み取れた全テキスト",
            "venue_indicators": ["@", "at", "会場:", "VENUE"]
        }
        ```
        
        **注意事項:**
        - アーティスト名と会場名を混同しないよう注意
        - 複数の会場がある場合は全て抽出
        - 不確実な情報でも抽出し、confidenceで信頼度を表現
        """

        response = model.generate_content([uploaded_file, prompt])
        
        # JSON解析（既存のロジック）
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
        
        # 後処理：venue_nameが空の場合の補完ロジック改善
        if not result.get('venues'):
            # event_nameから会場っぽいものを抽出
            potential_venues = extract_venue_from_event_names(result.get('event_names', []))
            if potential_venues:
                result['venues'] = potential_venues
            else:
                result['venues'] = result.get('event_names', [])
        
        result["analysis_status"] = "success"
        result["raw_response"] = response.text
        
        return result
        
    except Exception as e:
        return {
            "analysis_status": "error",
            "error_message": f"Gemini API analysis failed: {str(e)}"
        }

def extract_venue_from_event_names(event_names: list) -> list:
    """
    イベント名から会場名らしいものを抽出
    """
    venue_keywords = ['club', 'hall', 'theater', 'studio', 'space', 'bar', 'lounge']
    potential_venues = []
    
    for name in event_names:
        name_lower = name.lower()
        if any(keyword in name_lower for keyword in venue_keywords):
            potential_venues.append(name)
    
    return potential_venues
```

----------------------------------------------
### 2. 検索システムの改善
----------------------------------------------
```python
from fuzzywuzzy import fuzz, process
import re
from typing import List, Tuple, Optional
import unicodedata

class VenueSearchEngine:
    def __init__(self, bq_client, project_id, dataset_id, table_id):
        self.bq_client = bq_client
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.table_id = table_id
        self.venues_cache = None
        self.refresh_cache()
    
    def refresh_cache(self):
        """BigQueryからvenue一覧をキャッシュ"""
        query = f"""
        SELECT place_id, display_name, formatted_address, latitude, longitude, 
               business_status, types
        FROM `{self.project_id}.{self.dataset_id}.{self.table_id}`
        """
        df = self.bq_client.query(query).to_dataframe()
        self.venues_cache = df.to_dict('records')
    
    def normalize_text(self, text: str) -> str:
        """テキスト正規化"""
        if not text:
            return ""
        
        # Unicode正規化
        text = unicodedata.normalize('NFKC', text)
        
        # 小文字化
        text = text.lower()
        
        # 特殊文字除去
        text = re.sub(r'[^\w\s]', '', text)
        
        # 余分な空白除去
        text = ' '.join(text.split())
        
        return text
    
    def multi_strategy_search(self, venue_name: str, location: str = "") -> List[Tuple[dict, float]]:
        """
        複数の検索戦略を組み合わせて会場を検索
        """
        if not self.venues_cache:
            return []
        
        results = []
        venue_norm = self.normalize_text(venue_name)
        location_norm = self.normalize_text(location)
        
        for venue in self.venues_cache:
            display_name = venue.get('display_name', '')
            address = venue.get('formatted_address', '')
            
            display_norm = self.normalize_text(display_name)
            address_norm = self.normalize_text(address)
            
            # 戦略1: 完全一致
            exact_score = self._exact_match_score(venue_norm, display_norm)
            
            # 戦略2: 部分一致
            partial_score = self._partial_match_score(venue_norm, display_norm)
            
            # 戦略3: ファジーマッチング
            fuzzy_score = fuzz.ratio(venue_norm, display_norm) / 100
            
            # 戦略4: 場所情報との組み合わせ
            location_boost = self._location_boost(location_norm, address_norm)
            
            # 戦略5: キーワードマッチング
            keyword_score = self._keyword_match_score(venue_norm, display_norm)
            
            # 総合スコア計算
            total_score = (
                exact_score * 0.4 +
                partial_score * 0.2 +
                fuzzy_score * 0.2 +
                keyword_score * 0.1 +
                location_boost * 0.1
            )
            
            if total_score > 0.3:  # 閾値
                results.append((venue, total_score))
        
        # スコア順でソート
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:5]  # 上位5件
    
    def _exact_match_score(self, query: str, target: str) -> float:
        """完全一致スコア"""
        return 1.0 if query == target else 0.0
    
    def _partial_match_score(self, query: str, target: str) -> float:
        """部分一致スコア"""
        if query in target:
            return len(query) / len(target)
        elif target in query:
            return len(target) / len(query)
        return 0.0
    
    def _location_boost(self, location: str, address: str) -> float:
        """場所情報によるブースト"""
        if not location or not address:
            return 0.0
        
        # 都市名、区名などが住所に含まれているかチェック
        location_words = location.split()
        for word in location_words:
            if len(word) > 1 and word in address:
                return 0.2
        return 0.0
    
    def _keyword_match_score(self, query: str, target: str) -> float:
        """キーワードマッチング"""
        query_words = set(query.split())
        target_words = set(target.split())
        
        if not query_words:
            return 0.0
        
        intersection = query_words.intersection(target_words)
        return len(intersection) / len(query_words)
    
    def search_venue(self, venue_name: str, location: str = "", 
                    min_score: float = 0.6) -> Optional[dict]:
        """
        会場検索のメインメソッド
        """
        results = self.multi_strategy_search(venue_name, location)
        
        if results and results[0][1] >= min_score:
            venue, score = results[0]
            venue = venue.copy()
            venue['_match_score'] = score
            venue['_search_method'] = 'multi_strategy'
            return venue
        
        return None

# 使用例
def get_venue_from_bigquery_improved(venue_name: str, location: str = "", 
                                   search_engine: VenueSearchEngine = None) -> Optional[Dict]:
    """
    改善された会場検索関数
    """
    if not search_engine:
        # グローバル変数から必要な情報を取得
        search_engine = VenueSearchEngine(bq_client, project_id, dataset_id, table_id)
    
    return search_engine.search_venue(venue_name, location)

# Elasticsearch/OpenSearchを使った検索（オプション）
def setup_elasticsearch_venue_search():
    """
    ElasticsearchやOpenSearchを使った高度な検索システム
    BigQueryと併用することでより高精度な検索が可能
    """
    from elasticsearch import Elasticsearch
    
    # Elasticsearch設定例
    es = Elasticsearch(['localhost:9200'])
    
    # インデックス作成
    index_mapping = {
        "mappings": {
            "properties": {
                "place_id": {"type": "keyword"},
                "display_name": {
                    "type": "text",
                    "analyzer": "standard",
                    "fields": {
                        "keyword": {"type": "keyword"},
                        "ngram": {
                            "type": "text",
                            "analyzer": "my_ngram_analyzer"
                        }
                    }
                },
                "formatted_address": {"type": "text"},
                "location": {"type": "geo_point"},
                "types": {"type": "keyword"}
            }
        },
        "settings": {
            "analysis": {
                "analyzer": {
                    "my_ngram_analyzer": {
                        "tokenizer": "my_ngram_tokenizer"
                    }
                },
                "tokenizer": {
                    "my_ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 3
                    }
                }
            }
        }
    }
    
    return es, index_mapping
```



----------------------------------------------
### 会場検索システム アーキテクチャ提案
----------------------------------------------
現在の課題

BigQueryの限界

ファジーマッチングが基本的
全文検索機能が限定的
リアルタイム検索に不向き


検索精度の問題

表記揺れに対応できない
部分一致の優先順位が不適切
地理的情報を活用できていない



推奨アーキテクチャ
レベル1: BigQuery + 改善されたロジック（短期）
Gemini解析 → 改善された検索ロジック → BigQuery → Places API
メリット:

既存システムの改良で実装が簡単
追加コストが少ない
検索精度は向上する

実装例:

複数の検索戦略を組み合わせ
キャッシュ機能でパフォーマンス向上
正規化ロジックの強化

レベル2: Hybrid検索システム（中期）
Gemini解析 → Elasticsearch/OpenSearch → BigQuery → Places API
                    ↑
              Vector Search (Embedding)
メリット:

自然言語処理による意味的検索
高速な全文検索
地理的検索の組み合わせ

技術スタック:

Elasticsearch/OpenSearch
SentenceTransformers (日本語対応)
Redis (キャッシュ)

レベル3: AI強化検索システム（長期）
Gemini解析 → LLM分類器 → Vector DB → Knowledge Graph → Places API
                              ↑
                        Named Entity Recognition
メリット:

文脈を理解した検索
関連性の高い候補提案
継続学習による精度向上

実装優先順位
Phase 1: 即座に実装可能（1-2週間）

Geminiプロンプトの改善

より具体的な抽出ルール
例示を含んだプロンプト
信頼度スコアの活用


BigQuery検索ロジックの改善

複数戦略の組み合わせ
正規化の強化
キャッシュ機能



Phase 2: 中期改善（1-2ヶ月）

Elasticsearchの導入
bash# Google Cloud Elasticsearch Service
gcloud elasticsearch instances create venue-search \
  --region=asia-northeast1 \
  --tier=standard \
  --size=3

ベクトル検索の追加
pythonfrom sentence_transformers import SentenceTransformer

# 日本語対応モデル
model = SentenceTransformer('sonoisa/sentence-bert-base-ja-mean-tokens')


Phase 3: 長期的改善（3-6ヶ月）

Knowledge Graphの構築

会場間の関係性をモデル化
エリア情報の階層化
イベントタイプとの関連付け


機械学習による検索最適化

ユーザーフィードバックの学習
A/Bテストによる継続改善



技術選定の指針
データ量別推奨

〜10,000会場: BigQuery + 改善ロジック
10,000〜100,000会場: Elasticsearch
100,000会場〜: Elasticsearch + Vector Search

パフォーマンス要件別

バッチ処理中心: BigQuery強化
リアルタイム検索: Elasticsearch
複雑な条件検索: Knowledge Graph

実装サンプル
最小限の改善（今すぐできる）
python# processフローの改善
def process_flyer_improved(image_path: str):
    # 1. Gemini解析の改善
    result = analyze_event_flyer_improved(image_path)
    
    # 2. 検索エンジンの初期化
    search_engine = VenueSearchEngine(bq_client, project_id, dataset_id, table_id)
    
    final_venues = []
    for venue_name in result.get("venues", []):
        # 3. 改善された検索
        location = result.get("location", [""])[0]
        venue_info = search_engine.search_venue(venue_name, location)
        
        # 4. Places API fallback
        if not venue_info:
            event_name = result.get("event_names", [""])[0]
            venue_info = search_google_places_new(event_name, venue_name, location)
            if venue_info:
                upsert_venue_to_bigquery(venue_info)
                search_engine.refresh_cache()  # キャッシュ更新
        
        if venue_info:
            final_venues.append(venue_info)
    
    result["venues_info"] = final_venues
    return result
次のステップ

Phase 1の実装から始める
検索精度の測定体制を整備
ユーザーフィードバックの収集機構
段階的にPhase 2, 3に移行