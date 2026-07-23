package com.aivle.bigproject.storage;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.time.Duration;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.InputStreamResource;
import org.springframework.core.io.Resource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.DeleteObjectRequest;
import software.amazon.awssdk.services.s3.model.GetObjectRequest;
import software.amazon.awssdk.services.s3.model.PutObjectRequest;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.GetObjectPresignRequest;

// 파일을 S3 버킷에 저장/조회/삭제하는 역할만 담당하는 클래스.
// FileStorageService(로컬)와 마찬가지로 Attachment 엔티티나 DB를 전혀 모름.
// 두 클래스는 서로 독립적 — 어느 한쪽을 지워도 다른 쪽은 그대로 동작함.
@Service
public class S3FileStorageService {

    private final S3Client s3Client;
    private final String bucket;

    public S3FileStorageService(S3Client s3Client,
                                @Value("${app.s3.bucket}") String bucket) {
        this.s3Client = s3Client;
        this.bucket = bucket;
    }

    // 파일을 {상담ID}/{uuid}_{원본파일명} 형태의 key로 S3에 업로드하고, 그 key를 돌려줌
    // (로컬 버전의 "rootDir 기준 상대경로"에 대응하는 개념 — 이 key를 DB(Attachment.fileUrl)에 저장)
    public String store(Long consultationId, MultipartFile file) {
        String originalName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "file";
        String key = consultationId + "/" + UUID.randomUUID() + "__" + originalName;

        try {
            s3Client.putObject(
                    PutObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .contentType(file.getContentType())
                            .build(),
                    RequestBody.fromInputStream(file.getInputStream(), file.getSize())
            );
        } catch (IOException e) {
            throw new UncheckedIOException("S3 업로드에 실패했습니다: " + originalName, e);
        }

        return key;
    }

    // 저장된 파일을 다운로드용 Resource로 읽어옴 (스트리밍 방식으로 S3에서 직접 받아옴)
    public Resource loadAsResource(String key) {
        try {
            var s3Object = s3Client.getObject(
                    GetObjectRequest.builder()
                            .bucket(bucket)
                            .key(key)
                            .build()
            );
            return new InputStreamResource(s3Object);
        } catch (Exception e) {
            throw new UncheckedIOException("S3에서 파일을 읽을 수 없습니다: " + key,
                    new IOException(e));
        }
    }

    // 클라이언트가 서버를 거치지 않고 S3에서 바로 다운로드할 수 있는 임시 URL 발급
    // (대용량 파일 다운로드 시 서버 부하를 줄이고 싶을 때 사용 — 필요 없으면 이 메서드만 안 쓰면 됨)
    public String getPresignedDownloadUrl(String key, Duration expiration) {
        try (S3Presigner presigner = S3Presigner.create()) {
            GetObjectRequest getObjectRequest = GetObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build();

            GetObjectPresignRequest presignRequest = GetObjectPresignRequest.builder()
                    .signatureDuration(expiration)
                    .getObjectRequest(getObjectRequest)
                    .build();

            return presigner.presignGetObject(presignRequest).url().toString();
        }
    }

    // 파일 삭제. Consultation/Attachment 삭제 시 같이 호출됨.
    public void delete(String key) {
        s3Client.deleteObject(
                DeleteObjectRequest.builder()
                        .bucket(bucket)
                        .key(key)
                        .build()
        );
    }
}