package com.aivle.bigproject.attachment;

import com.aivle.bigproject.consultation.Consultation;
import com.aivle.bigproject.consultation.ConsultationService;
import com.aivle.bigproject.storage.FileStorageService;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.multipart.MultipartFile;
import org.springframework.web.server.ResponseStatusException;

@Service
@Transactional(readOnly = true)
public class AttachmentService {

    private final AttachmentRepository attachmentRepository;
    private final ConsultationService consultationService; // 업로드 대상 상담이 실제로 있는지 확인용
    private final FileStorageService fileStorageService;   // 실제 파일 저장/읽기/삭제 담당

    public AttachmentService(AttachmentRepository attachmentRepository,
                              ConsultationService consultationService,
                              FileStorageService fileStorageService) {
        this.attachmentRepository = attachmentRepository;
        this.consultationService = consultationService;
        this.fileStorageService = fileStorageService;
    }

    @Transactional
    public Attachment upload(Long consultationId, MultipartFile file, String fileType) {
        // 1) 상담이 실제로 존재하는지 확인 (없으면 404)
        Consultation consultation = consultationService.findById(consultationId);
        // 2) 디스크에 파일 저장하고, 저장된 경로를 돌려받음
        String storedUrl = fileStorageService.store(consultationId, file);
        String originalName = file.getOriginalFilename() != null ? file.getOriginalFilename() : "file";
        // 3) DB에 첨부파일 정보(메타데이터) 저장
        return attachmentRepository.save(new Attachment(consultation, originalName, fileType, storedUrl));
    }

    // 다운로드/삭제 전에 "이 첨부파일이 진짜 이 상담 소속이 맞는지"까지 같이 검증하는 조회 메서드.
    // (다른 상담의 attachmentId를 URL에 넣어서 접근하는 걸 막기 위함)
    public Attachment findByIdForConsultation(Long consultationId, Long attachmentId) {
        Attachment attachment = attachmentRepository.findById(attachmentId)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "첨부파일을 찾을 수 없습니다: " + attachmentId));
        if (!attachment.getConsultation().getId().equals(consultationId)) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "첨부파일을 찾을 수 없습니다: " + attachmentId);
        }
        return attachment;
    }

    public Resource loadFile(Long consultationId, Long attachmentId) {
        Attachment attachment = findByIdForConsultation(consultationId, attachmentId);
        return fileStorageService.loadAsResource(attachment.getFileUrl());
    }

    @Transactional
    public void delete(Long consultationId, Long attachmentId) {
        Attachment attachment = findByIdForConsultation(consultationId, attachmentId);
        fileStorageService.delete(attachment.getFileUrl()); // 디스크 파일 삭제
        attachmentRepository.delete(attachment);              // DB row 삭제
    }
}
