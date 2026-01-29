"""
Document Type Classifier
Detects document type from content using LLM or pattern matching
"""

import logging
from typing import Dict, Optional, Tuple
import anthropic
import re

from config import CONFIG
from document_type_schemas import DOCUMENT_TYPE_SCHEMAS, get_all_document_types

logger = logging.getLogger(__name__)


class DocumentTypeClassifier:
    """Classify document type from content"""
    
    def __init__(self):
        """Initialize classifier"""
        self.anthropic_client = anthropic.Anthropic(
            api_key=CONFIG['anthropic']['api_key']
        )
        self.document_types = get_all_document_types()
        logger.info(f"Initialized DocumentTypeClassifier with {len(self.document_types)} document types")
    
    def classify(self, text: str, use_llm: bool = True) -> Tuple[str, float]:
        """
        Classify document type from text
        
        Args:
            text: Document text content
            use_llm: Whether to use LLM (True) or pattern matching (False)
            
        Returns:
            Tuple of (document_type, confidence_score)
        """
        if use_llm:
            return self._classify_with_llm(text)
        else:
            return self._classify_with_patterns(text)
    
    def _classify_with_llm(self, text: str) -> Tuple[str, float]:
        """
        Classify using LLM (Claude)
        
        Args:
            text: Document text
            
        Returns:
            Tuple of (document_type, confidence_score)
        """
        # Build list of document types for prompt
        type_list = []
        for doc_type, schema in DOCUMENT_TYPE_SCHEMAS.items():
            type_list.append(f"- {doc_type}: {schema['ar_name']} ({schema['en_name']})")
        
        system_prompt = f"""You are an expert at classifying Arabic legal documents for Qatar's judicial system.

Your task is to identify the document type from the content. Choose the most appropriate type from this list:

{chr(10).join(type_list)}

Return ONLY the document type identifier (e.g., "police_complaint", "court_judgment") and a confidence score (0.0-1.0).

Format your response as: TYPE|CONFIDENCE
Example: police_complaint|0.95"""

        user_prompt = f"""Classify this Arabic legal document:

{text[:10000]}"""  # Limit to 10k chars for classification

        try:
            message = self.anthropic_client.messages.create(
                model=CONFIG['anthropic']['model'],
                max_tokens=100,
                system=system_prompt,
                messages=[
                    {
                        "role": "user",
                        "content": user_prompt
                    }
                ]
            )
            
            response_text = message.content[0].text.strip()
            
            # Parse response
            if '|' in response_text:
                doc_type, confidence_str = response_text.split('|', 1)
                try:
                    confidence = float(confidence_str.strip())
                except ValueError:
                    confidence = 0.8
            else:
                doc_type = response_text.strip()
                confidence = 0.8
            
            # Validate document type
            if doc_type not in self.document_types:
                logger.warning(f"LLM returned unknown document type: {doc_type}, using pattern matching fallback")
                return self._classify_with_patterns(text)
            
            logger.info(f"Classified document as: {doc_type} (confidence: {confidence:.2f})")
            return (doc_type, confidence)
        
        except Exception as e:
            logger.error(f"Error in LLM classification: {str(e)}, falling back to pattern matching")
            return self._classify_with_patterns(text)
    
    def _classify_with_patterns(self, text: str) -> Tuple[str, float]:
        """
        Classify using pattern matching on Arabic keywords
        
        Args:
            text: Document text
            
        Returns:
            Tuple of (document_type, confidence_score)
        """
        # Arabic keywords/phrases for each document type
        patterns = {
            'police_complaint': [
                r'افادة\s+طرف',
                r'بلاغ\s+شرطة',
                r'شكوى'
            ],
            'police_statement': [
                r'افادة\s+أولية',
                r'إفادة\s+أولية'
            ],
            'investigation_record': [
                r'محضر\s+تحقيق',
                r'محضر\s+التحقيق'
            ],
            'detention_order': [
                r'حبس\s+احتياطي',
                r'أمر\s+حبس',
                r'أمر\s+الحبس'
            ],
            'detention_renewal': [
                r'تجديد\s+حبس',
                r'محضر\s+تجديد',
                r'تجديد\s+الحبس'
            ],
            'case_transfer_order': [
                r'أمر\s+إحالة',
                r'إحالة\s+القضية',
                r'نقل\s+القضية'
            ],
            'court_session': [
                r'محضر\s+الجلسة',
                r'محضر\s+جلسة',
                r'جلسة\s+الاستماع'
            ],
            'court_judgment': [
                r'حكم',
                r'الحكم',
                r'قرار\s+المحكمة'
            ],
            'court_summons': [
                r'إعلان',
                r'إخطار',
                r'استدعاء'
            ],
            'waiver': [
                r'تنازل',
                r'التنازل',
                r'تنازل\s+عن'
            ],
            'lab_test_results': [
                r'نتيجة\s+فحص',
                r'فحص\s+الكحول',
                r'نتائج\s+المختبر'
            ],
            'forensic_medical_report': [
                r'تقرير\s+الطب\s+الشرعي',
                r'الطب\s+الشرعي',
                r'تقرير\s+طبي'
            ],
            'enforcement_order': [
                r'تنفيذ\s+الأحكام',
                r'تنفيذ\s+الحكم',
                r'أمر\s+التنفيذ'
            ],
            'criminal_record_request': [
                r'صحيفة\s+الحالة\s+الجنائية',
                r'طلب\s+صحيفة',
                r'شهادة\s+السوابق'
            ],
            'administrative_correspondence': [
                r'مخاطبة\s+إدارية',
                r'مراسلة\s+إدارية',
                r'كتاب\s+إداري'
            ],
            'release_order': [
                r'أمر\s+إخلاء\s+السبيل',
                r'إخلاء\s+السبيل',
                r'أمر\s+الإفراج'
            ]
        }
        
        text_lower = text.lower()
        scores = {}
        
        for doc_type, pattern_list in patterns.items():
            score = 0.0
            matches = 0
            
            for pattern in pattern_list:
                if re.search(pattern, text_lower):
                    matches += 1
                    score += 0.3
            
            # Normalize score (max 0.9 for pattern matching)
            if matches > 0:
                score = min(0.9, score)
                scores[doc_type] = score
        
        if scores:
            # Return type with highest score
            best_type = max(scores.items(), key=lambda x: x[1])
            logger.info(f"Pattern matching classified as: {best_type[0]} (confidence: {best_type[1]:.2f})")
            return best_type
        
        # Default fallback
        logger.warning("Could not classify document type, defaulting to police_complaint")
        return ('police_complaint', 0.5)

