package com.aivle.bigproject.consultation;

import com.aivle.bigproject.attachment.Attachment;
import com.aivle.bigproject.consultation.dto.ConsultationRequest;
import com.aivle.bigproject.consultation.dto.ConsultationResponse;
import com.aivle.bigproject.storage.FileStorageService;
import com.aivle.bigproject.user.User;
import com.aivle.bigproject.user.UserService;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Transactional(readOnly = true)
public class ConsultationService {

    private final ConsultationRepository consultationRepository;
    private final FileStorageService fileStorageService; // 삭제 시 첨부파일을 디스크에서도 지우기 위해 필요
    private final UserService userService; // userId로 실제 User가 있는지 확인하기 위해 필요

    public ConsultationService(ConsultationRepository consultationRepository,
                                FileStorageService fileStorageService,
                                UserService userService) {
        this.consultationRepository = consultationRepository;
        this.fileStorageService = fileStorageService;
        this.userService = userService;
    }

    @Transactional
    public ConsultationResponse create(ConsultationRequest request) {
        // userId가 실제로 존재하는 User인지 먼저 확인 (없으면 UserService가 404를 던짐)
        User user = userService.findById(request.userId());
        Consultation saved = consultationRepository.save(
                new Consultation(user, request.title(), request.inputText(), request.opponentName()));
        // 여기서 바로 DTO로 변환 — 트랜잭션이 열려있는 동안 처리해야
        // ConsultationResponse.from()이 attachments(LAZY)를 문제없이 읽을 수 있음
        return ConsultationResponse.from(saved);
    }

    public List<ConsultationResponse> findAll() {
        return consultationRepository.findAll().stream()
                .map(ConsultationResponse::from)
                .toList();
    }

    // 컨트롤러가 쓰는 조회용 — 엔티티 대신 바로 응답 DTO를 반환
    public ConsultationResponse get(Long id) {
        return ConsultationResponse.from(findById(id));
    }

    // 이건 엔티티(Consultation) 자체를 반환하는 내부용 메서드.
    // AttachmentService가 "파일 업로드 대상 상담이 실제로 있는지" 확인하고
    // 그 엔티티를 FK로 연결할 때 사용함. 반드시 트랜잭션 안에서 호출해야 함.
    public Consultation findById(Long id) {
        return consultationRepository.findById(id)
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "상담을 찾을 수 없습니다: " + id));
    }

    // 부분 수정: request에서 null이 아닌 필드만 반영. 즉 status만 보내면 title/inputText는 그대로 유지됨.
    // userId(담당자 재배정)는 이 메서드에서 다루지 않음 — 아직 미구현 범위.
    @Transactional
    public ConsultationResponse update(Long id, ConsultationRequest request) {
        Consultation consultation = findById(id);
        if (request.title() != null) {
            consultation.setTitle(request.title());
        }
        if (request.inputText() != null) {
            consultation.setInputText(request.inputText());
        }
        if (request.opponentName() != null) {
            consultation.setOpponentName(request.opponentName());
        }
        if (request.status() != null) {
            consultation.setStatus(request.status());
        }
        // consultation은 이미 영속 상태(DB와 연결된 상태)라 setter만 호출해도
        // 트랜잭션이 끝날 때 JPA가 알아서 UPDATE 쿼리를 날림 (별도 save() 호출 불필요)
        return ConsultationResponse.from(consultation);
    }

    @Transactional
    public void delete(Long id) {
        Consultation consultation = findById(id);
        // DB row는 cascade 설정으로 자동 삭제되지만, 디스크에 저장된 실제 파일은
        // JPA가 모르는 영역이라 여기서 직접 하나씩 지워줘야 함
        for (Attachment attachment : consultation.getAttachments()) {
            fileStorageService.delete(attachment.getFileUrl());
        }
        consultationRepository.delete(consultation);
    }
}
