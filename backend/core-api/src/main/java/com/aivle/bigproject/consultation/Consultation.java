package com.aivle.bigproject.consultation;

import com.aivle.bigproject.attachment.Attachment;
import com.aivle.bigproject.user.User;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import java.time.LocalDateTime;
import java.util.ArrayList;
import java.util.List;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

// 상담 1건. ERD 기준 Main Table.
@Entity
@Getter
@Setter
@NoArgsConstructor
@EntityListeners(AuditingEntityListener.class)
public class Consultation {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    // 이 상담을 담당하는 상담원. 다대일(N:1) — 여러 상담이 같은 User를 가리킬 수 있음.
    // nullable=false라서 반드시 존재하는 User를 연결해야 저장 가능 (ConsultationService에서 검증함).
    @ManyToOne
    @JoinColumn(name = "user_id", nullable = false)
    private User user;

    @Column(nullable = false)
    private String title;

    // 상담 본문(텍스트로 직접 입력했거나, STT로 변환된 내용). 녹음파일만 있는 경우 null 가능.
    @Lob
    @Column(name = "input_text", columnDefinition = "TEXT")
    private String inputText;

    // 상대방 이름 — 유사 사건 집단화(clustering)에 참고용으로 쓰일 필드 (ERD 주석 기준)
    @Column(name = "opponent_name")
    private String opponentName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private ConsultationStatus status = ConsultationStatus.RECEIVED;

    // 이 상담에 딸린 첨부파일 목록. 1:N 관계.
    // cascade=ALL: Consultation을 저장/삭제하면 Attachment도 같이 저장/삭제됨
    // orphanRemoval=true: 이 리스트에서 Attachment를 빼면 DB에서도 자동 삭제됨
    // 기본적으로 LAZY 로딩이라, 트랜잭션이 열려있을 때만 접근 가능 (Service 계층 안에서 다뤄야 함)
    @OneToMany(mappedBy = "consultation", cascade = CascadeType.ALL, orphanRemoval = true)
    private List<Attachment> attachments = new ArrayList<>();

    @CreatedDate
    @Column(nullable = false, updatable = false)
    private LocalDateTime createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private LocalDateTime updatedAt;

    // 생성 시 필요한 필드만 받는 생성자
    public Consultation(User user, String title, String inputText, String opponentName) {
        this.user = user;
        this.title = title;
        this.inputText = inputText;
        this.opponentName = opponentName;
    }
}
