package com.aivle.bigproject.common.exception;

import jakarta.servlet.http.HttpServletRequest;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

// 예전엔 각 서비스(UserService, ConsultationService, AttachmentService, AiAnalysisService)가
// 직접 ResponseStatusException을 던져서 404를 만들었는데, 코드가 4곳에서 반복돼서 여기로 모음.
// @RestControllerAdvice가 붙으면 모든 @RestController에서 발생한 해당 예외를 가로채서
// 여기 정의한 방식으로만 응답하게 됨.
//
// 응답 형식은 원래 Spring Boot 기본 에러 포맷(docs/api.md에 이미 문서화된 timestamp/status/error/
// message/path 구조)과 똑같이 맞춰서, 이 리팩터링으로 API 응답 모양이 바뀌지 않도록 함.
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(NotFoundException.class)
    public ResponseEntity<Map<String, Object>> handleNotFound(NotFoundException e, HttpServletRequest request) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
                .body(errorBody(HttpStatus.NOT_FOUND, e.getMessage(), request));
    }

    private Map<String, Object> errorBody(HttpStatus status, String message, HttpServletRequest request) {
        Map<String, Object> body = new LinkedHashMap<>();
        body.put("timestamp", Instant.now().toString());
        body.put("status", status.value());
        body.put("error", status.getReasonPhrase());
        body.put("message", message);
        body.put("path", request.getRequestURI());
        return body;
    }
}
