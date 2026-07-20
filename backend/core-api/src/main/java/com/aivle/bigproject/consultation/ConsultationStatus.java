package com.aivle.bigproject.consultation;

// 상담 진행 상태. 생성 시 항상 RECEIVED로 시작.
public enum ConsultationStatus {
    RECEIVED,   // 접수됨
    ANALYZING,  // AI 분석 중
    COMPLETED   // 완료
}
