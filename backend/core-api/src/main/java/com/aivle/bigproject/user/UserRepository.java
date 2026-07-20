package com.aivle.bigproject.user;

import org.springframework.data.jpa.repository.JpaRepository;

// JpaRepository만 상속받으면 save/findById/findAll/delete 등이 기본 제공됨 (직접 구현 X)
public interface UserRepository extends JpaRepository<User, Long> {
}
