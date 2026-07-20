package com.aivle.bigproject.analysis;

import java.util.List;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AiAnalysisRepository extends JpaRepository<AiAnalysis, Long> {

    // 메서드 이름만으로 Spring Data가 "consultation.id로 조회"하는 쿼리를 자동 생성함 (JPQL 직접 안 씀)
    List<AiAnalysis> findByConsultationId(Long consultationId);

    // 상담이 삭제될 때 딸린 분석 결과도 같이 지우기 위해 사용 (ConsultationService.delete 참고)
    void deleteByConsultationId(Long consultationId);
}
