package com.aivle.bigproject.consultation.dto;

import com.aivle.bigproject.consultation.ConsultationStatus;

// 생성(POST)과 수정(PUT) 요청에 공통으로 쓰는 DTO.
// 수정 시엔 null이 아닌 필드만 반영됨 (ConsultationService.update 참고) — 즉 "부분 수정" 방식.
// 생성 시엔 status를 보내도 무시되고 항상 RECEIVED로 시작함 (ConsultationService.create 참고).
public record ConsultationRequest(
        Long userId,
        String title,
        String inputText,
        String opponentName,
        ConsultationStatus status
) {
}
