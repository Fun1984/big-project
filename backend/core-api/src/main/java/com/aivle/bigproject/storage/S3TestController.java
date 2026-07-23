package com.aivle.bigproject.storage;

import org.springframework.core.io.Resource;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

// 테스트 끝나면 반드시 삭제할 것 — 실제 서비스 코드가 아님
@RestController
@RequestMapping("/test/s3")
public class S3TestController {

    private final S3FileStorageService s3FileStorageService;

    public S3TestController(S3FileStorageService s3FileStorageService) {
        this.s3FileStorageService = s3FileStorageService;
    }

    @PostMapping("/upload")
    public String upload(@RequestParam("file") MultipartFile file) {
        return s3FileStorageService.store(1L, file); // 반환된 key를 눈으로 확인
    }

    @GetMapping("/download")
    public ResponseEntity<Resource> download(@RequestParam String key) {
        Resource resource = s3FileStorageService.loadAsResource(key);
        return ResponseEntity.ok()
                .header("Content-Disposition", "attachment")
                .body(resource);
    }

    @GetMapping("/presigned-url")
    public String presignedUrl(@RequestParam String key) {
        return s3FileStorageService.getPresignedDownloadUrl(key, java.time.Duration.ofMinutes(10));
    }

    @DeleteMapping("/delete")
    public String delete(@RequestParam String key) {
        s3FileStorageService.delete(key);
        return "deleted: " + key;
    }
}