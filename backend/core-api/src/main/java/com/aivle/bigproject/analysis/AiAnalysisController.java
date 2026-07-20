package com.aivle.bigproject.analysis;

import com.aivle.bigproject.analysis.dto.AiAnalysisRequest;
import com.aivle.bigproject.analysis.dto.AiAnalysisResponse;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AiAnalysisController {

    private final AiAnalysisService aiAnalysisService;

    public AiAnalysisController(AiAnalysisService aiAnalysisService) {
        this.aiAnalysisService = aiAnalysisService;
    }

    // POST /api/consultations/{consultationId}/analyses
    // ai-api가 분석 파이프라인을 돌리고 난 뒤 그 결과를 여기로 저장하게 될 엔드포인트
    @PostMapping("/api/consultations/{consultationId}/analyses")
    @ResponseStatus(HttpStatus.CREATED)
    public AiAnalysisResponse create(@PathVariable Long consultationId, @RequestBody AiAnalysisRequest request) {
        return aiAnalysisService.create(consultationId, request);
    }

    // GET /api/consultations/{consultationId}/analyses — 해당 상담의 분석 결과 전체 (재분석 이력 포함)
    @GetMapping("/api/consultations/{consultationId}/analyses")
    public List<AiAnalysisResponse> findAll(@PathVariable Long consultationId) {
        return aiAnalysisService.findAllByConsultation(consultationId);
    }

    // GET /api/consultations/{consultationId}/analyses/{analysisId} — 단건 조회
    @GetMapping("/api/consultations/{consultationId}/analyses/{analysisId}")
    public AiAnalysisResponse get(@PathVariable Long consultationId, @PathVariable Long analysisId) {
        return aiAnalysisService.get(consultationId, analysisId);
    }

    // PUT /api/consultations/{consultationId}/analyses/{analysisId} — 부분 수정
    @PutMapping("/api/consultations/{consultationId}/analyses/{analysisId}")
    public AiAnalysisResponse update(@PathVariable Long consultationId, @PathVariable Long analysisId,
                                      @RequestBody AiAnalysisRequest request) {
        return aiAnalysisService.update(consultationId, analysisId, request);
    }

    // DELETE /api/consultations/{consultationId}/analyses/{analysisId}
    @DeleteMapping("/api/consultations/{consultationId}/analyses/{analysisId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long consultationId, @PathVariable Long analysisId) {
        aiAnalysisService.delete(consultationId, analysisId);
    }
}
