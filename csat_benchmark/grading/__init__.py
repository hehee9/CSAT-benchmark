"""@description 수능 답안 추출·단일 생성 채점 정책 공개"""

from .extractor import AnswerVerifier
from .single import VerificationResult, verify_hard_single_result, verify_single_result

__all__ = [
    "AnswerVerifier",
    "VerificationResult",
    "verify_hard_single_result",
    "verify_single_result",
]
