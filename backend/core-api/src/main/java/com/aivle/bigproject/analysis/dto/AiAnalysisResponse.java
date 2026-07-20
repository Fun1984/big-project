package com.aivle.bigproject.analysis.dto;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;
import java.time.LocalDateTime;

// contracts/ai_analysis_mock.json과 필드명이 1:1로 맞도록 만든 응답 형태.
// @JsonNaming(SnakeCaseStrategy)가 analysisId -> analysis_id, caseType -> case_type 식으로
// 자동 변환해줘서, 이 파일의 필드는 그대로 두고 이름만 계약서 형식(snake_case)으로 나감.
// extracted_json 등은 JsonNode 타입이라 문자열이 아니라 실제 중첩 JSON 객체/배열로 응답에 실림.
//
// 엔티티 -> 이 DTO로 변환하는 작업은 AiAnalysisService에서 함 (JSON 문자열 -> JsonNode 파싱이
// 필요해서 단순 정적 팩토리 메서드로는 못 하고 ObjectMapper가 있어야 함).
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AiAnalysisResponse(
        Long analysisId,
        Long consultationId,
        String summary,
        String caseType,
        String caseSubtype,
        String urgencyLevel,
        String eligibility,
        JsonNode extractedJson,
        JsonNode missingInfoJson,
        JsonNode checklistJson,
        JsonNode recommendationJson,
        JsonNode timelineJson,
        JsonNode clusterResultJson,
        String estimatedTime,
        LocalDateTime createdAt
) {
}
