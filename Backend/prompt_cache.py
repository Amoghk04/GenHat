"""
Prompt caching system for GenHat Backend
Stores prompts and their responses to avoid redundant API calls
Uses semantic similarity to find similar prompts
"""

import json
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from hashlib import sha256
import logging

logger = logging.getLogger(__name__)


class PromptCache:
    """
    Cache system for storing prompts and their responses.
    Uses exact matching and semantic similarity for lookup.
    """
    
    def __init__(self, cache_dir: Path, similarity_threshold: float = 0.85):
        """
        Initialize prompt cache
        
        Args:
            cache_dir: Directory to store cache files
            similarity_threshold: Threshold for considering prompts similar (0-1)
        """
        self.cache_dir = cache_dir
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.cache_file = self.cache_dir / "prompt_cache.json"
        self.similarity_threshold = similarity_threshold
        self.cache_data: Dict[str, Dict[str, Any]] = {}
        self._load_cache()
        
        # Try to load sentence transformers for similarity
        self.embedding_model = None
        try:
            from sentence_transformers import SentenceTransformer
            self.embedding_model = SentenceTransformer('all-MiniLM-L12-v2')
            logger.info("✅ Loaded embedding model for prompt similarity")
        except ImportError:
            logger.warning("⚠️ sentence-transformers not available, using exact match only")
    
    def _load_cache(self):
        """Load cache from disk"""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self.cache_data = json.load(f)
                logger.info(f"📦 Loaded {len(self.cache_data)} cached prompts")
            except Exception as e:
                logger.error(f"❌ Error loading cache: {e}")
                self.cache_data = {}
    
    def _save_cache(self):
        """Save cache to disk"""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self.cache_data, f, indent=2)
            logger.info(f"💾 Saved cache with {len(self.cache_data)} entries")
        except Exception as e:
            logger.error(f"❌ Error saving cache: {e}")
    
    def _hash_prompt(self, prompt: str) -> str:
        """Generate hash for a prompt"""
        return sha256(prompt.encode('utf-8')).hexdigest()
    
    def _compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute similarity between two texts using embeddings
        Returns similarity score between 0 and 1
        """
        if not self.embedding_model:
            # Fallback to simple exact match
            return 1.0 if text1 == text2 else 0.0
        
        try:
            from sklearn.metrics.pairwise import cosine_similarity
            import numpy as np
            
            embeddings = self.embedding_model.encode([text1, text2])
            similarity = cosine_similarity([embeddings[0]], [embeddings[1]])[0][0]
            return float(similarity)
        except Exception as e:
            logger.error(f"❌ Error computing similarity: {e}")
            return 0.0
    
    def get(self, prompt: str, context: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Get cached response for a prompt
        
        Args:
            prompt: The prompt text to search for
            context: Optional context (persona, task, etc.) for better matching
            
        Returns:
            Cached response data or None if not found
        """
        # Try exact match first
        prompt_hash = self._hash_prompt(prompt)
        if prompt_hash in self.cache_data:
            entry = self.cache_data[prompt_hash]
            logger.info(f"✅ Exact cache hit for prompt (hash: {prompt_hash[:8]}...)")
            entry['cache_hit_type'] = 'exact'
            entry['cache_hit_time'] = datetime.now().isoformat()
            return entry
        
        # Try similarity search if embedding model is available
        if self.embedding_model:
            best_match = None
            best_score = 0.0
            
            for cached_hash, entry in self.cache_data.items():
                cached_prompt = entry.get('prompt', '')
                similarity = self._compute_similarity(prompt, cached_prompt)
                
                # Also consider context similarity if provided
                if context and entry.get('context'):
                    context_similarity = self._compute_context_similarity(context, entry['context'])
                    # Weighted average: 70% prompt, 30% context
                    similarity = 0.7 * similarity + 0.3 * context_similarity
                
                if similarity > best_score and similarity >= self.similarity_threshold:
                    best_score = similarity
                    best_match = entry
            
            if best_match:
                logger.info(f"✅ Similar cache hit (similarity: {best_score:.2%})")
                best_match['cache_hit_type'] = 'similar'
                best_match['cache_hit_time'] = datetime.now().isoformat()
                best_match['similarity_score'] = best_score
                return best_match
        
        logger.info("❌ No cache hit for prompt")
        return None
    
    def _compute_context_similarity(self, context1: Dict[str, Any], context2: Dict[str, Any]) -> float:
        """Compute similarity between two context dictionaries"""
        # Enforce project_name match if present
        if context1.get('project_name') != context2.get('project_name'):
            return 0.0

        # Handle chunk_hashes for content similarity (Jaccard similarity)
        if 'chunk_hashes' in context1 and 'chunk_hashes' in context2:
            hashes1 = set(context1['chunk_hashes'])
            hashes2 = set(context2['chunk_hashes'])
            
            if not hashes1 and not hashes2:
                return 1.0
            if not hashes1 or not hashes2:
                return 0.0
                
            intersection = len(hashes1 & hashes2)
            union = len(hashes1 | hashes2)
            return intersection / union

        # Simple field-by-field comparison for other cases
        common_keys = set(context1.keys()) & set(context2.keys())
        if not common_keys:
            return 0.0
        
        matches = sum(1 for key in common_keys if context1[key] == context2[key])
        return matches / len(common_keys)
    
    def set(self, prompt: str, response: str, context: Optional[Dict[str, Any]] = None, 
            metadata: Optional[Dict[str, Any]] = None):
        """
        Store a prompt and its response in cache
        
        Args:
            prompt: The prompt text
            response: The response text
            context: Optional context (persona, task, etc.)
            metadata: Optional metadata (model, domain, etc.)
        """
        prompt_hash = self._hash_prompt(prompt)
        
        entry = {
            'prompt': prompt,
            'response': response,
            'context': context or {},
            'metadata': metadata or {},
            'created_at': datetime.now().isoformat(),
            'access_count': 0,
            'last_accessed': None
        }
        
        self.cache_data[prompt_hash] = entry
        self._save_cache()
        logger.info(f"💾 Cached prompt (hash: {prompt_hash[:8]}...)")
    
    def update_access(self, prompt: str):
        """Update access count and timestamp for a cached prompt"""
        prompt_hash = self._hash_prompt(prompt)
        if prompt_hash in self.cache_data:
            self.cache_data[prompt_hash]['access_count'] += 1
            self.cache_data[prompt_hash]['last_accessed'] = datetime.now().isoformat()
            self._save_cache()
    
    def clear(self):
        """Clear all cached entries"""
        self.cache_data = {}
        self._save_cache()
        logger.info("🗑️ Cleared prompt cache")
    
    def stats(self) -> Dict[str, Any]:
        """Get cache statistics"""
        total_entries = len(self.cache_data)
        total_accesses = sum(entry.get('access_count', 0) for entry in self.cache_data.values())
        
        return {
            'total_entries': total_entries,
            'total_accesses': total_accesses,
            'cache_file': str(self.cache_file),
            'similarity_enabled': self.embedding_model is not None,
            'similarity_threshold': self.similarity_threshold
        }
    
    def get_all_entries(self) -> List[Dict[str, Any]]:
        """Get all cache entries for inspection"""
        entries = []
        for prompt_hash, entry in self.cache_data.items():
            entries.append({
                'hash': prompt_hash,
                'prompt_preview': entry['prompt'][:100] + '...' if len(entry['prompt']) > 100 else entry['prompt'],
                'response_preview': entry['response'][:100] + '...' if len(entry['response']) > 100 else entry['response'],
                'created_at': entry['created_at'],
                'access_count': entry.get('access_count', 0),
                'last_accessed': entry.get('last_accessed'),
                'context': entry.get('context', {})
            })
        return sorted(entries, key=lambda x: x['created_at'], reverse=True)
    
    def remove_old_entries(self, days: int = 30):
        """Remove entries older than specified days"""
        from datetime import timedelta
        
        cutoff_date = datetime.now() - timedelta(days=days)
        removed_count = 0
        
        for prompt_hash, entry in self.cache_data.items():
            created_at = datetime.fromisoformat(entry['created_at'])
            if created_at < cutoff_date:
                del self.cache_data[prompt_hash]
                removed_count += 1
        
        if removed_count > 0:
            self._save_cache()
            logger.info(f"🗑️ Removed {removed_count} old cache entries")
        
        return removed_count
