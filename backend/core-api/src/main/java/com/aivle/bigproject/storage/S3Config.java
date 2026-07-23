package com.aivle.bigproject.storage;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import software.amazon.awssdk.auth.credentials.AwsBasicCredentials;
import software.amazon.awssdk.auth.credentials.AwsCredentialsProvider;
import software.amazon.awssdk.auth.credentials.DefaultCredentialsProvider;
import software.amazon.awssdk.auth.credentials.StaticCredentialsProvider;
import software.amazon.awssdk.regions.Region;
import software.amazon.awssdk.services.s3.S3Client;

// S3Client 빈을 만드는 설정 클래스.
// FileStorageService(로컬)와는 완전히 독립적 — 이 설정이 없어도 로컬 저장은 그대로 동작함.
@Configuration
public class S3Config {

    @Value("${app.s3.region}")
    private String region;

    @Value("${app.s3.access-key:}")
    private String accessKey;

    @Value("${app.s3.secret-key:}")
    private String secretKey;

    @Bean
    public S3Client s3Client() {
        AwsCredentialsProvider credentialsProvider =
                (accessKey != null && !accessKey.isBlank())
                        ? StaticCredentialsProvider.create(
                        AwsBasicCredentials.create(accessKey, secretKey))
                        : DefaultCredentialsProvider.create(); // access-key 없으면 IAM role 등 기본 체인 사용

        return S3Client.builder()
                .region(Region.of(region))
                .credentialsProvider(credentialsProvider)
                .build();
    }
}