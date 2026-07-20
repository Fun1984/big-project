package com.aivle.bigproject.attachment.dto;

import com.aivle.bigproject.attachment.Attachment;
import java.time.LocalDateTime;

public record AttachmentResponse(
        Long id,
        String fileName,
        String fileType,
        String extractedText,
        LocalDateTime uploadedAt,
        // 실제 저장 경로(fileUrl)를 그대로 노출하지 않고, 우리 API를 거쳐서
        // 다운로드할 수 있는 링크를 계산해서 내려줌 (저장 방식이 나중에 S3로 바뀌어도
        // 클라이언트가 쓰는 이 downloadUrl 형식은 그대로 유지 가능)
        String downloadUrl
) {
    public static AttachmentResponse from(Attachment attachment) {
        return new AttachmentResponse(
                attachment.getId(),
                attachment.getFileName(),
                attachment.getFileType(),
                attachment.getExtractedText(),
                attachment.getUploadedAt(),
                "/api/consultations/%d/attachments/%d".formatted(
                        attachment.getConsultation().getId(), attachment.getId())
        );
    }
}
