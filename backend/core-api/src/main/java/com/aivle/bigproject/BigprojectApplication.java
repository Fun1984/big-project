package com.aivle.bigproject;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@SpringBootApplication
// @EnableJpaAuditing: 엔티티의 createdAt/updatedAt 필드를 저장/수정 시점에 자동으로 채워줌
@EnableJpaAuditing
public class BigprojectApplication {

	public static void main(String[] args) {
		SpringApplication.run(BigprojectApplication.class, args);
	}

}
