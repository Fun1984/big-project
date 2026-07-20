package com.aivle.bigproject.user;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EntityListeners;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.LocalDateTime;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

// 상담원(사용자) 계정. Consultation이 이 엔티티를 FK로 참조한다.
@Entity
// "user"는 PostgreSQL 예약어라 테이블명으로 못 써서 users로 지정
@Table(name = "users")
@Getter
@Setter
@NoArgsConstructor // JPA는 파라미터 없는 생성자가 필수라서 Lombok으로 자동 생성
@EntityListeners(AuditingEntityListener.class) // createdAt/updatedAt 자동 기록 활성화
public class User {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY) // DB가 auto-increment로 값 채움
    private Long id;

    @Column(nullable = false)
    private String name;

    @Enumerated(EnumType.STRING) // enum을 숫자(0,1..)가 아니라 "CONSULTANT" 같은 문자열로 저장
    @Column(nullable = false)
    private UserRole role;

    @Column(nullable = false, unique = true)
    private String email;

    // 로그인/비밀번호 기능은 아직 구현 안 함 — 컬럼만 미리 만들어둔 상태.
    // 인증 작업 시작하면 이 필드에 해시된 비밀번호를 저장하게 될 예정.
    @Column(name = "password_hash")
    private String passwordHash;

    @CreatedDate
    @Column(nullable = false, updatable = false) // 생성 시 한 번만 기록, 이후 수정 불가
    private LocalDateTime createdAt;

    @LastModifiedDate
    @Column(nullable = false)
    private LocalDateTime updatedAt;

    // 생성 시 필요한 필드만 받는 생성자 (id/시간은 자동으로 채워짐)
    public User(String name, UserRole role, String email) {
        this.name = name;
        this.role = role;
        this.email = email;
    }
}
