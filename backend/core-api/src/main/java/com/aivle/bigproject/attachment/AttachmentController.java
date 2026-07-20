package com.aivle.bigproject.attachment;

import com.aivle.bigproject.attachment.dto.AttachmentResponse;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.DeleteMapping;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.multipart.MultipartFile;

@RestController
public class AttachmentController {

    private final AttachmentService attachmentService;

    public AttachmentController(AttachmentService attachmentService) {
        this.attachmentService = attachmentService;
    }

    // POST /api/consultations/{consultationId}/attachments — 파일 업로드
    // JSON이 아니라 multipart/form-data로 받음 (file: 실제 파일, fileType: 문자열)
    @PostMapping("/api/consultations/{consultationId}/attachments")
    @ResponseStatus(HttpStatus.CREATED)
    public AttachmentResponse upload(@PathVariable Long consultationId,
                                      @RequestParam("file") MultipartFile file,
                                      @RequestParam("fileType") String fileType) {
        return AttachmentResponse.from(attachmentService.upload(consultationId, file, fileType));
    }

    // GET /api/consultations/{consultationId}/attachments/{attachmentId} — 파일 원본 다운로드
    @GetMapping("/api/consultations/{consultationId}/attachments/{attachmentId}")
    public ResponseEntity<Resource> download(@PathVariable Long consultationId, @PathVariable Long attachmentId) {
        Attachment attachment = attachmentService.findByIdForConsultation(consultationId, attachmentId);
        Resource resource = attachmentService.loadFile(consultationId, attachmentId);
        return ResponseEntity.ok()
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                // 브라우저가 파일을 열지 않고 "다운로드"하도록 지시하는 헤더, 원본 파일명도 같이 전달
                .header(HttpHeaders.CONTENT_DISPOSITION, "attachment; filename=\"" + attachment.getFileName() + "\"")
                .body(resource);
    }

    // DELETE /api/consultations/{consultationId}/attachments/{attachmentId} — 첨부파일 삭제
    @DeleteMapping("/api/consultations/{consultationId}/attachments/{attachmentId}")
    @ResponseStatus(HttpStatus.NO_CONTENT)
    public void delete(@PathVariable Long consultationId, @PathVariable Long attachmentId) {
        attachmentService.delete(consultationId, attachmentId);
    }
}
