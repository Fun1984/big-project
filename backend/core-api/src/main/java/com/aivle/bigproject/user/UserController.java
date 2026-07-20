package com.aivle.bigproject.user;

import com.aivle.bigproject.user.dto.UserRequest;
import com.aivle.bigproject.user.dto.UserResponse;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

// HTTP 요청을 받아서 UserService에 그대로 위임하는 계층.
// 여기엔 업무 로직을 넣지 않고, "요청을 받아서 → 서비스 호출 → 응답 반환"만 함.
@RestController
public class UserController {

    private final UserService userService;

    public UserController(UserService userService) {
        this.userService = userService;
    }

    // POST /api/users — 상담원 생성
    @PostMapping("/api/users")
    @ResponseStatus(HttpStatus.CREATED) // 201 Created
    public UserResponse create(@RequestBody UserRequest request) {
        return userService.create(request);
    }

    // GET /api/users — 전체 목록
    @GetMapping("/api/users")
    public List<UserResponse> findAll() {
        return userService.findAll();
    }

    // GET /api/users/{id} — 단건 조회, 없으면 UserService에서 404 던짐
    @GetMapping("/api/users/{id}")
    public UserResponse findById(@PathVariable Long id) {
        return userService.get(id);
    }
}
