package com.aivle.bigproject.storage;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.Resource;
import org.springframework.core.io.UrlResource;
import org.springframework.stereotype.Service;
import org.springframework.web.multipart.MultipartFile;

// 파일을 로컬 디스크에 저장/조회/삭제하는 역할만 담당하는 클래스.
// Attachment 엔티티나 DB를 전혀 모름 — 오직 "파일 다루기"만 함 (관심사 분리).
// 나중에 저장소를 S3 등으로 바꾸고 싶으면 이 클래스만 교체하면 됨.
@Service
public class FileStorageService {

    private final Path rootDir; // 모든 파일이 저장되는 최상위 폴더 (기본값: ./uploads)

    // application.yaml의 app.upload-dir 값을 주입받음
    public FileStorageService(@Value("${app.upload-dir}") String uploadDir) {
        this.rootDir = Path.of(uploadDir).toAbsolutePath().normalize();
        try {
            Files.createDirectories(rootDir); // 폴더 없으면 서버 시작 시 미리 만들어둠
        } catch (IOException e) {
            throw new UncheckedIOException("업로드 디렉토리를 생성할 수 없습니다: " + rootDir, e);
        }
    }

    // 파일을 uploads/{상담ID}/{uuid}_{원본파일명} 형태로 저장하고, rootDir 기준 상대경로를 돌려줌
    public String store(Long consultationId, MultipartFile file) {
        String originalName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "file";
        // 같은 이름 파일이 여러 번 업로드돼도 안 겹치도록 UUID를 앞에 붙임
        String storedName = UUID.randomUUID() + "_" + originalName;
        Path targetDir = rootDir.resolve(String.valueOf(consultationId)).normalize();
        Path target = targetDir.resolve(storedName).normalize();
        // 파일명에 "../" 같은 게 섞여 rootDir 바깥으로 벗어나려는 시도를 차단 (경로 조작 공격 방지)
        if (!target.startsWith(rootDir)) {
            throw new IllegalArgumentException("잘못된 파일 이름입니다: " + originalName);
        }
        try {
            Files.createDirectories(targetDir);
            file.transferTo(target);
        } catch (IOException e) {
            throw new UncheckedIOException("파일 저장에 실패했습니다: " + originalName, e);
        }
        return rootDir.relativize(target).toString(); // DB(Attachment.fileUrl)에 저장할 상대경로
    }

    // 저장된 파일을 다운로드용 Resource로 읽어옴
    public Resource loadAsResource(String relativePath) {
        Path file = rootDir.resolve(relativePath).normalize();
        if (!file.startsWith(rootDir)) {
            throw new IllegalArgumentException("잘못된 파일 경로입니다: " + relativePath);
        }
        try {
            return new UrlResource(file.toUri());
        } catch (IOException e) {
            throw new UncheckedIOException("파일을 읽을 수 없습니다: " + relativePath, e);
        }
    }

    // 파일 삭제. Consultation/Attachment 삭제 시 같이 호출됨.
    public void delete(String relativePath) {
        Path file = rootDir.resolve(relativePath).normalize();
        if (!file.startsWith(rootDir)) {
            throw new IllegalArgumentException("잘못된 파일 경로입니다: " + relativePath);
        }
        try {
            Files.deleteIfExists(file);
        } catch (IOException e) {
            throw new UncheckedIOException("파일 삭제에 실패했습니다: " + relativePath, e);
        }
    }
}
