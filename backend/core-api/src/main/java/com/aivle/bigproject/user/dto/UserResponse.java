package com.aivle.bigproject.user.dto;

import com.aivle.bigproject.user.User;
import com.aivle.bigproject.user.UserRole;
import java.time.LocalDateTime;

// API 응답으로 내려줄 형태. passwordHash는 절대 포함하지 않음 (민감정보라 응답에서 제외).
public record UserResponse(
        Long id,
        String name,
        UserRole role,
        String email,
        LocalDateTime createdAt,
        LocalDateTime updatedAt
) {
    // 엔티티(User) → 응답 DTO로 변환하는 정적 팩토리 메서드
    public static UserResponse from(User user) {
        return new UserResponse(
                user.getId(),
                user.getName(),
                user.getRole(),
                user.getEmail(),
                user.getCreatedAt(),
                user.getUpdatedAt()
        );
    }
}
