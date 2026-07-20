package com.aivle.bigproject.common.exception;

// "id로 찾았는데 없음" 상황을 표현하는 공통 예외.
// User/Consultation/Attachment/AiAnalysis 서비스가 전부 이 예외를 던지고,
// 실제 HTTP 404 응답으로 바꾸는 건 GlobalExceptionHandler가 한 곳에서 처리함.
public class NotFoundException extends RuntimeException {
    public NotFoundException(String message) {
        super(message);
    }
}
