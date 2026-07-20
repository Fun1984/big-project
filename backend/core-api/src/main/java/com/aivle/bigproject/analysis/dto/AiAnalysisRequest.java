package com.aivle.bigproject.analysis.dto;

import tools.jackson.databind.JsonNode;
import tools.jackson.databind.PropertyNamingStrategies;
import tools.jackson.databind.annotation.JsonNaming;

// 생성/수정 요청 body.
// consultation_id는 요청에 안 넣음 — URL 경로(/api/consultations/{consultationId}/analyses)에서
// 이미 받기 때문. (Attachment 업로드 때 consultationId를 경로로만 받는 것과 같은 방식)
//
// @JsonNaming(SnakeCaseStrategy): Java 필드는 camelCase(caseType)로 쓰되, 실제 JSON은
// snake_case(case_type)로 주고받도록 자동 변환 — contracts/ai_analysis_mock.json과 필드명을
// 맞추기 위한 설정.
@JsonNaming(PropertyNamingStrategies.SnakeCaseStrategy.class)
public record AiAnalysisRequest(
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
        String estimatedTime
) {
}
