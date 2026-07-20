package com.aivle.bigproject.analysis;

import com.aivle.bigproject.analysis.dto.AiAnalysisRequest;
import com.aivle.bigproject.analysis.dto.AiAnalysisResponse;
import com.aivle.bigproject.common.exception.NotFoundException;
import com.aivle.bigproject.consultation.Consultation;
import com.aivle.bigproject.consultation.ConsultationService;
import tools.jackson.core.JacksonException;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.ObjectMapper;
import java.util.List;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class AiAnalysisService {

    private final AiAnalysisRepository aiAnalysisRepository;
    private final ConsultationService consultationService; // 대상 상담이 실제 있는지 확인용
    private final ObjectMapper objectMapper; // jsonb 컬럼(String)과 JsonNode를 서로 변환하는 데 사용

    public AiAnalysisService(AiAnalysisRepository aiAnalysisRepository,
                              ConsultationService consultationService,
                              ObjectMapper objectMapper) {
        this.aiAnalysisRepository = aiAnalysisRepository;
        this.consultationService = consultationService;
        this.objectMapper = objectMapper;
    }

    @Transactional
    public AiAnalysisResponse create(Long consultationId, AiAnalysisRequest request) {
        Consultation consultation = consultationService.findById(consultationId);
        AiAnalysis analysis = new AiAnalysis(
                consultation,
                request.summary(),
                request.caseType(),
                request.caseSubtype(),
                request.urgencyLevel(),
                request.eligibility(),
                toJsonText(request.extractedJson()),
                toJsonText(request.missingInfoJson()),
                toJsonText(request.checklistJson()),
                toJsonText(request.recommendationJson()),
                toJsonText(request.timelineJson()),
                toJsonText(request.clusterResultJson()),
                request.estimatedTime()
        );
        return toResponse(aiAnalysisRepository.save(analysis));
    }

    public List<AiAnalysisResponse> findAllByConsultation(Long consultationId) {
        consultationService.findById(consultationId); // 없는 상담이면 여기서 404
        return aiAnalysisRepository.findByConsultationId(consultationId).stream()
                .map(this::toResponse)
                .toList();
    }

    public AiAnalysisResponse get(Long consultationId, Long analysisId) {
        return toResponse(findByIdForConsultation(consultationId, analysisId));
    }

    // attachment 쪽과 같은 이유: analysisId만 보고 찾지 않고, 그게 진짜 이 상담 소속인지까지 확인
    private AiAnalysis findByIdForConsultation(Long consultationId, Long analysisId) {
        AiAnalysis analysis = aiAnalysisRepository.findById(analysisId)
                .orElseThrow(() -> new NotFoundException("분석 결과를 찾을 수 없습니다: " + analysisId));
        if (!analysis.getConsultation().getId().equals(consultationId)) {
            throw new NotFoundException("분석 결과를 찾을 수 없습니다: " + analysisId);
        }
        return analysis;
    }

    // Consultation.update()와 같은 방식: request에서 null이 아닌 필드만 반영 (부분 수정)
    @Transactional
    public AiAnalysisResponse update(Long consultationId, Long analysisId, AiAnalysisRequest request) {
        AiAnalysis analysis = findByIdForConsultation(consultationId, analysisId);
        if (request.summary() != null) {
            analysis.setSummary(request.summary());
        }
        if (request.caseType() != null) {
            analysis.setCaseType(request.caseType());
        }
        if (request.caseSubtype() != null) {
            analysis.setCaseSubtype(request.caseSubtype());
        }
        if (request.urgencyLevel() != null) {
            analysis.setUrgencyLevel(request.urgencyLevel());
        }
        if (request.eligibility() != null) {
            analysis.setEligibility(request.eligibility());
        }
        if (request.extractedJson() != null) {
            analysis.setExtractedJson(toJsonText(request.extractedJson()));
        }
        if (request.missingInfoJson() != null) {
            analysis.setMissingInfoJson(toJsonText(request.missingInfoJson()));
        }
        if (request.checklistJson() != null) {
            analysis.setChecklistJson(toJsonText(request.checklistJson()));
        }
        if (request.recommendationJson() != null) {
            analysis.setRecommendationJson(toJsonText(request.recommendationJson()));
        }
        if (request.timelineJson() != null) {
            analysis.setTimelineJson(toJsonText(request.timelineJson()));
        }
        if (request.clusterResultJson() != null) {
            analysis.setClusterResultJson(toJsonText(request.clusterResultJson()));
        }
        if (request.estimatedTime() != null) {
            analysis.setEstimatedTime(request.estimatedTime());
        }
        return toResponse(analysis);
    }

    @Transactional
    public void delete(Long consultationId, Long analysisId) {
        AiAnalysis analysis = findByIdForConsultation(consultationId, analysisId);
        aiAnalysisRepository.delete(analysis);
    }

    // 요청으로 받은 JsonNode -> DB(jsonb 컬럼)에 넣을 원본 JSON 텍스트
    private String toJsonText(JsonNode node) {
        return node == null ? null : node.toString();
    }

    // 엔티티 -> 응답 DTO. DTO 변환을 컨트롤러가 아니라 여기(서비스, 트랜잭션 안)에서 하는 이유는
    // Consultation 쪽과 동일 — consultation은 지연 로딩이라 트랜잭션 밖에서 접근하면 에러 남.
    private AiAnalysisResponse toResponse(AiAnalysis a) {
        return new AiAnalysisResponse(
                a.getId(),
                a.getConsultation().getId(),
                a.getSummary(),
                a.getCaseType(),
                a.getCaseSubtype(),
                a.getUrgencyLevel(),
                a.getEligibility(),
                parseJson(a.getExtractedJson()),
                parseJson(a.getMissingInfoJson()),
                parseJson(a.getChecklistJson()),
                parseJson(a.getRecommendationJson()),
                parseJson(a.getTimelineJson()),
                parseJson(a.getClusterResultJson()),
                a.getEstimatedTime(),
                a.getCreatedAt()
        );
    }

    // DB에 저장된 원본 JSON 텍스트 -> 응답에 실릴 JsonNode로 파싱
    private JsonNode parseJson(String raw) {
        if (raw == null) {
            return null;
        }
        try {
            return objectMapper.readTree(raw);
        } catch (JacksonException e) {
            // jsonb 컬럼엔 항상 유효한 JSON만 들어있어야 하므로, 여기 걸리면 데이터 자체의 문제
            // (참고: Jackson 3부터는 JsonProcessingException 같은 checked 예외가 없어지고
            //  JacksonException이 unchecked로 통일됨)
            throw new IllegalStateException("저장된 JSON 데이터를 읽는 중 오류가 발생했습니다", e);
        }
    }
}
