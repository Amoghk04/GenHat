from rank_bm25 import BM25Okapi
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from typing import List, Dict, Any, Optional
import re
import numpy as np
from difflib import SequenceMatcher

class HybridRetriever:
    def __init__(self, domain: Optional[str] = None, embedding_model: str = "paraphrase-MiniLM-L3-v2"):
        """
        Hybrid retriever combining BM25 and sentence embeddings
        
        Args:
            domain: Domain for optimization ('travel', 'research', 'business', 'culinary', 'general')
            embedding_model: Sentence transformer model name
        """
        self.bm25 = None
        self.embedding_model = None
        self.chunks = []
        self.chunk_embeddings = None
        self.domain = domain or 'general'
        
        # Initialize embedding model
        try:
            self.embedding_model = SentenceTransformer(embedding_model)
            print(f"✅ Loaded embedding model: {embedding_model}")
        except Exception as e:
            print(f"⚠️ Could not load embedding model: {e}")
            print("⚠️ Falling back to BM25-only mode")
            self.embedding_model = None
        
        # Enhanced stop words for better tokenization
        self.stop_words = {
            'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for',
            'of', 'with', 'by', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
            'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'could',
            'should', 'may', 'might', 'can', 'this', 'that', 'these', 'those',
            'it', 'its', 'they', 'them', 'their', 'we', 'us', 'our', 'you', 'your',
            'he', 'she', 'his', 'her', 'him', 'i', 'me', 'my', 'myself'
        }
        
        # Domain-specific query expansions
        self.query_expansions = {
            'travel': {
                'trip': ['vacation', 'journey', 'travel', 'visit', 'tour'],
                'hotel': ['accommodation', 'lodging', 'stay', 'resort', 'inn'],
                'restaurant': ['dining', 'food', 'cuisine', 'meal', 'eatery'],
                'attraction': ['sight', 'landmark', 'destination', 'place', 'spot'],
                'transport': ['transportation', 'travel', 'commute', 'journey']
            },
            'research': {
                'study': ['research', 'analysis', 'investigation', 'examination'],
                'method': ['approach', 'technique', 'procedure', 'methodology'],
                'result': ['finding', 'outcome', 'conclusion', 'discovery'],
                'data': ['information', 'evidence', 'statistics', 'figures']
            },
            'business': {
                'form': ['document', 'template', 'application', 'form', 'paperwork'],
                'compliance': ['regulation', 'policy', 'requirement', 'standard'],
                'process': ['procedure', 'workflow', 'system', 'method'],
                'management': ['administration', 'oversight', 'supervision']
            },
            'culinary': {
                'recipe': ['dish', 'meal', 'cooking', 'preparation'],
                'ingredient': ['component', 'element', 'item', 'material'],
                'cooking': ['preparation', 'making', 'creating', 'preparing'],
                'meal': ['dish', 'course', 'serving', 'food']
            }
        }
        
        # Domain-specific BM25 parameters
        self.bm25_params = {
            'travel': {'k1': 1.2, 'b': 0.75},
            'research': {'k1': 1.5, 'b': 0.6},
            'business': {'k1': 1.0, 'b': 0.8},
            'culinary': {'k1': 1.3, 'b': 0.7},
            'general': {'k1': 1.2, 'b': 0.75}
        }
        
        # Hybrid scoring weights (can be tuned per domain)
        self.hybrid_weights = {
            'travel': {'bm25': 0.6, 'embedding': 0.4},      # BM25 good for location names
            'research': {'bm25': 0.4, 'embedding': 0.6},    # Embeddings good for concepts
            'business': {'bm25': 0.5, 'embedding': 0.5},    # Balanced
            'culinary': {'bm25': 0.7, 'embedding': 0.3},    # BM25 good for ingredients
            'general': {'bm25': 0.6, 'embedding': 0.4}      # Default
        }
    
    def enhanced_tokenization(self, text: str) -> List[str]:
        """Enhanced tokenization with stop word removal and filtering"""
        tokens = re.findall(r'\b\w+\b', text.lower())
        tokens = [token for token in tokens 
                 if token not in self.stop_words and len(token) > 2]
        return tokens
    
    def enhance_query(self, query: str, persona: str = "", task: str = "") -> str:
        """Enhance query with domain-specific expansions"""
        enhanced_query = query
        
        # Determine domain from persona and task
        domain_keywords = {
            'travel': ['travel', 'trip', 'vacation', 'tourist', 'planner', 'itinerary'],
            'research': ['research', 'study', 'analysis', 'investigation', 'academic'],
            'business': ['business', 'professional', 'hr', 'compliance', 'management'],
            'culinary': ['food', 'cooking', 'recipe', 'chef', 'culinary', 'menu']
        }
        
        # Find matching domain
        query_lower = query.lower()
        detected_domain = 'general'
        for domain, keywords in domain_keywords.items():
            if any(keyword in query_lower for keyword in keywords):
                detected_domain = domain
                break
        
        # Apply domain-specific expansions
        if detected_domain in self.query_expansions:
            for original, synonyms in self.query_expansions[detected_domain].items():
                if original in query_lower:
                    enhanced_query += ' ' + ' '.join(synonyms)
        
        return enhanced_query
    
    def weighted_text_representation(self, chunk: Dict[str, Any]) -> str:
        """Create weighted text representation with emphasis on headings"""
        heading = chunk.get('heading', '')
        content = chunk.get('content', '')
        
        # Give more weight to headings (they're more important)
        weighted_text = f"{heading} {heading} {content}"
        
        # Add document type weighting based on filename
        if 'pdf_name' in chunk:
            filename = chunk['pdf_name'].lower()
            
            # Culinary domain enhancements
            if 'main' in filename:
                weighted_text += ' main dish recipe'
            elif 'side' in filename:
                weighted_text += ' side dish accompaniment'
            elif 'breakfast' in filename:
                weighted_text += ' breakfast meal morning'
            elif 'lunch' in filename:
                weighted_text += ' lunch meal midday'
            elif 'dinner' in filename:
                weighted_text += ' dinner meal evening'
            
            # Travel domain enhancements
            elif 'cities' in filename:
                weighted_text += ' city urban destination'
            elif 'hotels' in filename:
                weighted_text += ' accommodation lodging stay'
            elif 'restaurants' in filename:
                weighted_text += ' dining food cuisine'
            elif 'things to do' in filename:
                weighted_text += ' activities attractions sights'
            
            # Business domain enhancements
            elif 'create' in filename or 'convert' in filename:
                weighted_text += ' creation conversion setup'
            elif 'edit' in filename:
                weighted_text += ' editing modification change'
            elif 'export' in filename:
                weighted_text += ' exportation output'
            elif 'fill' in filename or 'sign' in filename:
                weighted_text += ' form filling signature'
        
        return weighted_text
    
    def similarity_score(self, text1: str, text2: str) -> float:
        """Calculate similarity between two texts"""
        return SequenceMatcher(None, text1.lower(), text2.lower()).ratio()
    
    def diverse_top_k(self, scores: List[float], k: int = 5, diversity_threshold: float = 0.3) -> List[int]:
        """Select diverse top-k results to avoid similar chunks"""
        selected = []
        remaining = list(range(len(scores)))
        
        while len(selected) < k and remaining:
            # Get best remaining score
            best_idx = max(remaining, key=lambda i: scores[i])
            selected.append(best_idx)
            remaining.remove(best_idx)
            
            # Remove similar chunks
            best_chunk = self.chunks[best_idx]
            similar_indices = []
            
            for idx in remaining:
                chunk = self.chunks[idx]
                # Check if chunks are from same document or have similar headings
                if (chunk['pdf_name'] == best_chunk['pdf_name'] or 
                    self.similarity_score(chunk.get('heading', ''), best_chunk.get('heading', '')) > diversity_threshold):
                    similar_indices.append(idx)
            
            remaining = [idx for idx in remaining if idx not in similar_indices]
        
        return selected
    
    def build_index(self, chunks: List[Dict[str, Any]]):
        """Build hybrid index (BM25 + embeddings) from chunks"""
        self.chunks = chunks
        
        # Build BM25 index
        print("🔍 Building BM25 index...")
        params = self.bm25_params.get(self.domain, self.bm25_params['general'])
        tokenized_chunks = []
        
        for chunk in chunks:
            weighted_text = self.weighted_text_representation(chunk)
            tokens = self.enhanced_tokenization(weighted_text)
            tokenized_chunks.append(tokens)
        
        self.bm25 = BM25Okapi(tokenized_chunks, **params)
        
        # Build embeddings index
        if self.embedding_model:
            print("🔍 Building embeddings index...")
            chunk_texts = []
            for chunk in chunks:
                weighted_text = self.weighted_text_representation(chunk)
                chunk_texts.append(weighted_text)
            
            # Compute embeddings
            self.chunk_embeddings = self.embedding_model.encode(chunk_texts, show_progress_bar=True)
            print(f"✅ Computed embeddings for {len(chunks)} chunks")
        else:
            print("⚠️ Skipping embeddings (model not available)")
        
        return self
    
    def search_top_k(self, query: str, persona: str = "", task: str = "", k: int = 5) -> List[Dict[str, Any]]:
        """Search for top-k most relevant chunks using hybrid approach"""
        if not self.bm25:
            raise ValueError("Index not built. Call build_index() first.")
        
        # Enhance query
        enhanced_query = self.enhance_query(query, persona, task)
        
        # Get BM25 scores
        query_tokens = self.enhanced_tokenization(enhanced_query)
        bm25_scores = self.bm25.get_scores(query_tokens)
        
        # Normalize BM25 scores to [0, 1]
        if max(bm25_scores) > 0:
            bm25_scores = [score / max(bm25_scores) for score in bm25_scores]
        
        # Get embedding scores if available
        embedding_scores = None
        if self.embedding_model and self.chunk_embeddings is not None:
            query_embedding = self.embedding_model.encode([enhanced_query])
            similarities = cosine_similarity(query_embedding, self.chunk_embeddings)[0]
            embedding_scores = similarities.tolist()
        
        # Combine scores
        if embedding_scores:
            weights = self.hybrid_weights.get(self.domain, self.hybrid_weights['general'])
            hybrid_scores = [
                weights['bm25'] * bm25_score + weights['embedding'] * embedding_score
                for bm25_score, embedding_score in zip(bm25_scores, embedding_scores)
            ]
            print(f"🔍 Hybrid search (BM25: {weights['bm25']:.1f}, Embedding: {weights['embedding']:.1f})")
        else:
            hybrid_scores = bm25_scores
            print("🔍 BM25-only search (embeddings not available)")
        
        # Get diverse top-k indices
        top_indices = self.diverse_top_k(hybrid_scores, k)
        
        # Return top chunks with detailed scoring information
        top_chunks = []
        for rank, idx in enumerate(top_indices, 1):
            chunk = self.chunks[idx].copy()
            chunk['importance_rank'] = rank
            chunk['hybrid_score'] = hybrid_scores[idx]
            chunk['bm25_score'] = bm25_scores[idx]
            if embedding_scores:
                chunk['embedding_score'] = embedding_scores[idx]
            chunk['original_query'] = query
            chunk['enhanced_query'] = enhanced_query
            top_chunks.append(chunk)
        
        return top_chunks
    
    def get_scoring_breakdown(self, query: str, persona: str = "", task: str = "", k: int = 5) -> Dict[str, Any]:
        """Get detailed scoring breakdown for analysis"""
        if not self.bm25:
            raise ValueError("Index not built. Call build_index() first.")
        
        # Enhance query
        enhanced_query = self.enhance_query(query, persona, task)
        
        # Get individual scores
        query_tokens = self.enhanced_tokenization(enhanced_query)
        bm25_scores = self.bm25.get_scores(query_tokens)
        
        # Normalize BM25 scores
        if max(bm25_scores) > 0:
            bm25_scores = [score / max(bm25_scores) for score in bm25_scores]
        
        embedding_scores = None
        if self.embedding_model and self.chunk_embeddings is not None:
            query_embedding = self.embedding_model.encode([enhanced_query])
            similarities = cosine_similarity(query_embedding, self.chunk_embeddings)[0]
            embedding_scores = similarities.tolist()
        
        # Get weights
        weights = self.hybrid_weights.get(self.domain, self.hybrid_weights['general'])
        
        # Get top results
        top_chunks = self.search_top_k(query, persona, task, k)
        
        return {
            'query': query,
            'enhanced_query': enhanced_query,
            'domain': self.domain,
            'weights': weights,
            'top_chunks': top_chunks,
            'all_bm25_scores': bm25_scores,
            'all_embedding_scores': embedding_scores,
            'embedding_model': 'paraphrase-MiniLM-L3-v2' if self.embedding_model else None
        }

def build_hybrid_index(chunks: List[Dict[str, Any]], domain: Optional[str] = None, embedding_model: str = "paraphrase-MiniLM-L3-v2") -> HybridRetriever:
    """Build hybrid BM25 + embeddings index from chunks"""
    retriever = HybridRetriever(domain, embedding_model)
    retriever.build_index(chunks)
    return retriever

def search_top_k_hybrid(retriever: HybridRetriever, query: str, persona: str = "", task: str = "", k: int = 5) -> List[Dict[str, Any]]:
    """Search for top-k most relevant chunks using hybrid approach"""
    return retriever.search_top_k(query, persona, task, k) 