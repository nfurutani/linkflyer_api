import time
import json
import hashlib
import os
from typing import Dict, Optional, Any
from datetime import datetime, timedelta

class CacheManager:
    """
    シンプルなファイルベースキャッシュマネージャー
    BigQueryの結果とAPI呼び出し結果をキャッシュ
    """
    
    def __init__(self, cache_dir: str = "cache", default_ttl: int = 3600):
        """
        Args:
            cache_dir: キャッシュファイルを保存するディレクトリ
            default_ttl: デフォルトのキャッシュ有効期限（秒）
        """
        self.cache_dir = cache_dir
        self.default_ttl = default_ttl
        
        # キャッシュディレクトリを作成
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
    
    def _generate_cache_key(self, key_data: str) -> str:
        """キャッシュキーのハッシュを生成"""
        return hashlib.md5(key_data.encode('utf-8')).hexdigest()
    
    def _get_cache_path(self, cache_key: str) -> str:
        """キャッシュファイルのパスを生成"""
        return os.path.join(self.cache_dir, f"{cache_key}.json")
    
    def get(self, key: str, category: str = "general") -> Optional[Dict]:
        """
        キャッシュからデータを取得
        
        Args:
            key: キャッシュキー
            category: キャッシュのカテゴリ（bigquery, api, gemini等）
        
        Returns:
            キャッシュされたデータまたはNone
        """
        cache_key = self._generate_cache_key(f"{category}:{key}")
        cache_path = self._get_cache_path(cache_key)
        
        if not os.path.exists(cache_path):
            return None
        
        try:
            with open(cache_path, 'r', encoding='utf-8') as f:
                cache_data = json.load(f)
            
            # TTLチェック
            if cache_data.get('expires_at'):
                expires_at = datetime.fromisoformat(cache_data['expires_at'])
                if datetime.now() > expires_at:
                    # 期限切れのキャッシュを削除
                    os.unlink(cache_path)
                    return None
            
            print(f"🔄 Cache hit: {category}:{key}")
            return cache_data.get('data')
            
        except Exception as e:
            print(f"⚠️ Cache read error: {e}")
            # エラーファイルを削除
            try:
                os.unlink(cache_path)
            except:
                pass
            return None
    
    def set(self, key: str, data: Any, category: str = "general", ttl: Optional[int] = None) -> None:
        """
        データをキャッシュに保存
        
        Args:
            key: キャッシュキー
            data: 保存するデータ
            category: キャッシュのカテゴリ
            ttl: キャッシュ有効期限（秒）、Noneの場合はdefault_ttlを使用
        """
        cache_key = self._generate_cache_key(f"{category}:{key}")
        cache_path = self._get_cache_path(cache_key)
        
        if ttl is None:
            ttl = self.default_ttl
        
        expires_at = datetime.now() + timedelta(seconds=ttl)
        
        cache_data = {
            'data': data,
            'created_at': datetime.now().isoformat(),
            'expires_at': expires_at.isoformat(),
            'ttl': ttl,
            'key': key,
            'category': category
        }
        
        try:
            with open(cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2, default=str)
            
            print(f"💾 Cached: {category}:{key} (TTL: {ttl}s)")
            
        except Exception as e:
            print(f"⚠️ Cache write error: {e}")
    
    def clear_category(self, category: str) -> int:
        """指定カテゴリのキャッシュをクリア"""
        cleared_count = 0
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                cache_path = os.path.join(self.cache_dir, filename)
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    if cache_data.get('category') == category:
                        os.unlink(cache_path)
                        cleared_count += 1
                        
                except Exception:
                    pass
        
        print(f"🗑️ Cleared {cleared_count} cache entries for category: {category}")
        return cleared_count
    
    def clear_expired(self) -> int:
        """期限切れキャッシュをクリア"""
        cleared_count = 0
        now = datetime.now()
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                cache_path = os.path.join(self.cache_dir, filename)
                try:
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    if cache_data.get('expires_at'):
                        expires_at = datetime.fromisoformat(cache_data['expires_at'])
                        if now > expires_at:
                            os.unlink(cache_path)
                            cleared_count += 1
                            
                except Exception:
                    # 読み込めないファイルは削除
                    try:
                        os.unlink(cache_path)
                        cleared_count += 1
                    except:
                        pass
        
        print(f"🗑️ Cleared {cleared_count} expired cache entries")
        return cleared_count
    
    def clear_all(self) -> int:
        """全キャッシュをクリア"""
        cleared_count = 0
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                cache_path = os.path.join(self.cache_dir, filename)
                try:
                    os.unlink(cache_path)
                    cleared_count += 1
                except Exception:
                    pass
        
        print(f"🗑️ Cleared all {cleared_count} cache entries")
        return cleared_count
    
    def get_stats(self) -> Dict:
        """キャッシュの統計情報を取得"""
        stats = {
            'total_files': 0,
            'categories': {},
            'total_size_bytes': 0,
            'expired_count': 0
        }
        
        now = datetime.now()
        
        for filename in os.listdir(self.cache_dir):
            if filename.endswith('.json'):
                cache_path = os.path.join(self.cache_dir, filename)
                try:
                    # ファイルサイズ
                    stats['total_size_bytes'] += os.path.getsize(cache_path)
                    stats['total_files'] += 1
                    
                    # キャッシュデータ読み込み
                    with open(cache_path, 'r', encoding='utf-8') as f:
                        cache_data = json.load(f)
                    
                    category = cache_data.get('category', 'unknown')
                    if category not in stats['categories']:
                        stats['categories'][category] = 0
                    stats['categories'][category] += 1
                    
                    # 期限切れチェック
                    if cache_data.get('expires_at'):
                        expires_at = datetime.fromisoformat(cache_data['expires_at'])
                        if now > expires_at:
                            stats['expired_count'] += 1
                            
                except Exception:
                    pass
        
        stats['total_size_mb'] = round(stats['total_size_bytes'] / (1024 * 1024), 2)
        return stats


class VenueCache:
    """
    会場検索専用のキャッシュヘルパー
    """
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    def get_bigquery_result(self, venue_name: str, location_hints: str = "") -> Optional[Dict]:
        """BigQuery検索結果のキャッシュを取得"""
        cache_key = f"venue_search:{venue_name}:{location_hints}"
        return self.cache.get(cache_key, category="bigquery")
    
    def set_bigquery_result(self, venue_name: str, location_hints: str, result: Dict, ttl: int = 1800) -> None:
        """BigQuery検索結果をキャッシュ（30分）"""
        cache_key = f"venue_search:{venue_name}:{location_hints}"
        self.cache.set(cache_key, result, category="bigquery", ttl=ttl)
    
    def get_places_api_result(self, venue_name: str, location: str) -> Optional[Dict]:
        """Places API検索結果のキャッシュを取得"""
        cache_key = f"places_search:{venue_name}:{location}"
        return self.cache.get(cache_key, category="places_api")
    
    def set_places_api_result(self, venue_name: str, location: str, result: Dict, ttl: int = 3600) -> None:
        """Places API検索結果をキャッシュ（1時間）"""
        cache_key = f"places_search:{venue_name}:{location}"
        self.cache.set(cache_key, result, category="places_api", ttl=ttl)
    
    def get_venue_detail(self, place_id: str) -> Optional[Dict]:
        """会場詳細情報のキャッシュを取得"""
        return self.cache.get(place_id, category="venue_detail")
    
    def set_venue_detail(self, place_id: str, result: Dict, ttl: int = 7200) -> None:
        """会場詳細情報をキャッシュ（2時間）"""
        self.cache.set(place_id, result, category="venue_detail", ttl=ttl)


class GeminiCache:
    """
    Gemini分析専用のキャッシュヘルパー
    """
    
    def __init__(self, cache_manager: CacheManager):
        self.cache = cache_manager
    
    def get_analysis_result(self, image_path: str) -> Optional[Dict]:
        """画像分析結果のキャッシュを取得"""
        # ファイルの更新時間とサイズを含めてキーを生成
        try:
            if os.path.exists(image_path):
                stat = os.stat(image_path)
                cache_key = f"{image_path}:{stat.st_mtime}:{stat.st_size}"
            else:
                # URLの場合
                cache_key = image_path
            
            return self.cache.get(cache_key, category="gemini")
        except Exception:
            return None
    
    def set_analysis_result(self, image_path: str, result: Dict, ttl: int = 86400) -> None:
        """画像分析結果をキャッシュ（24時間）"""
        try:
            if os.path.exists(image_path):
                stat = os.stat(image_path)
                cache_key = f"{image_path}:{stat.st_mtime}:{stat.st_size}"
            else:
                # URLの場合
                cache_key = image_path
            
            self.cache.set(cache_key, result, category="gemini", ttl=ttl)
        except Exception as e:
            print(f"⚠️ Failed to cache Gemini result: {e}")


# 使用例
if __name__ == "__main__":
    # 基本的な使用例
    cache = CacheManager("cache", default_ttl=3600)
    
    # データを保存
    cache.set("test_key", {"data": "test_value"}, category="test")
    
    # データを取得
    result = cache.get("test_key", category="test")
    print(f"Retrieved: {result}")
    
    # 統計情報
    stats = cache.get_stats()
    print(f"Cache stats: {stats}")
    
    # 会場キャッシュの使用例
    venue_cache = VenueCache(cache)
    venue_cache.set_bigquery_result("test_venue", "Tokyo", {"place_id": "test123"})
    cached_venue = venue_cache.get_bigquery_result("test_venue", "Tokyo")
    print(f"Cached venue: {cached_venue}")