package com.aivle.bigproject.user.dto;

import com.aivle.bigproject.user.UserRole;

// POST /api/users 요청 body를 받는 그릇.
// 엔티티(User)를 직접 받지 않고 DTO를 따로 두는 이유:
//  - 클라이언트가 id/createdAt 같은 값을 마음대로 못 넣게 막기 위해
//  - API 요청 형식과 DB 구조를 분리해서, 나중에 DB가 바뀌어도 API는 안 바뀌게 하기 위해
public record UserRequest(String name, UserRole role, String email) {
}
