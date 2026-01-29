"""
Arabic Text Normalization Utilities
Handles Arabic text normalization for deduplication and matching
"""

import re
import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class ArabicNormalizer:
    """Normalize Arabic text for deduplication and matching"""
    
    @staticmethod
    def normalize_name(name: str) -> str:
        """
        Normalize Arabic name for deduplication
        
        Args:
            name: Arabic name string
            
        Returns:
            Normalized name (lowercase, no diacritics, normalized variants)
        """
        if not name:
            return ""
        
        # Remove extra whitespace
        normalized = ' '.join(name.strip().split())
        
        # Remove diacritics (harakat) and tatweel
        normalized = re.sub(r'[\u0640\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]', '', normalized)
        
        # Normalize common letter variants
        # Alif variants: أ, إ, آ → ا
        normalized = normalized.replace('أ', 'ا').replace('إ', 'ا').replace('آ', 'ا')
        
        # Ya variants: ى → ي (but preserve final alif maqsura in some contexts)
        normalized = normalized.replace('ى', 'ي')
        
        # Ta marbuta: ة → ه
        normalized = normalized.replace('ة', 'ه')
        
        # Remove extra spaces again after replacements
        normalized = ' '.join(normalized.split())
        
        # Convert to lowercase for consistent matching
        normalized = normalized.lower()
        
        return normalized
    
    @staticmethod
    def generate_party_signature(party: Dict[str, Any]) -> Optional[str]:
        """
        Generate deduplication signature for a party
        
        Priority: personal_id > normalized Arabic name > normalized English name
        
        Args:
            party: Party dictionary with name_ar, name_en, personal_id
            
        Returns:
            Signature string or None
        """
        # Priority 1: Personal ID (strongest identifier)
        personal_id = party.get('personal_id')
        if personal_id:
            return f"id:{str(personal_id).strip()}"
        
        # Priority 2: Normalized Arabic name
        name_ar = party.get('name_ar', '')
        if name_ar:
            normalized_ar = ArabicNormalizer.normalize_name(name_ar)
            if normalized_ar:
                return f"ar:{normalized_ar}"
        
        # Priority 3: Normalized English name (fallback)
        name_en = party.get('name_en', '')
        if name_en:
            normalized_en = name_en.strip().lower()
            if normalized_en:
                return f"en:{normalized_en}"
        
        return None
    
    @staticmethod
    def generate_charge_signature(charge: Dict[str, Any]) -> Optional[str]:
        """
        Generate deduplication signature for a charge
        
        Priority: article_number > normalized Arabic description
        
        Args:
            charge: Charge dictionary with article_number, description_ar, description_en
            
        Returns:
            Signature string or None
        """
        # Priority 1: Article number
        article = charge.get('article_number', '')
        if article:
            return f"art:{str(article).strip()}"
        
        # Priority 2: Normalized Arabic description
        desc_ar = charge.get('description_ar', '')
        if desc_ar:
            normalized_ar = ArabicNormalizer.normalize_name(desc_ar)
            if normalized_ar:
                return f"desc_ar:{normalized_ar}"
        
        # Priority 3: Normalized English description
        desc_en = charge.get('description_en', '')
        if desc_en:
            normalized_en = desc_en.strip().lower()
            if normalized_en:
                return f"desc_en:{normalized_en}"
        
        return None
    
    @staticmethod
    def generate_evidence_signature(evidence: Dict[str, Any]) -> Optional[str]:
        """
        Generate deduplication signature for evidence
        
        Uses: type + normalized Arabic description
        
        Args:
            evidence: Evidence dictionary with type, description_ar, description_en
            
        Returns:
            Signature string or None
        """
        ev_type = (evidence.get('type') or '').strip()
        desc_ar = evidence.get('description_ar', '')
        
        if ev_type and desc_ar:
            normalized_ar = ArabicNormalizer.normalize_name(desc_ar)
            if normalized_ar:
                return f"{ev_type}:{normalized_ar}"
        
        if desc_ar:
            normalized_ar = ArabicNormalizer.normalize_name(desc_ar)
            if normalized_ar:
                return f"desc_ar:{normalized_ar}"
        
        desc_en = evidence.get('description_en', '')
        if desc_en:
            normalized_en = desc_en.strip().lower()
            if normalized_en:
                return f"desc_en:{normalized_en}"
        
        return None
    
    @staticmethod
    def preserve_english_and_numbers(text: str) -> str:
        """
        Preserve English words and numbers in Arabic text
        
        Args:
            text: Text that may contain Arabic, English, and numbers
            
        Returns:
            Text with English/numbers preserved
        """
        # This is a placeholder - in practice, we want to preserve English words
        # and numbers as-is while normalizing Arabic parts
        # For now, return as-is since we handle normalization separately
        return text

