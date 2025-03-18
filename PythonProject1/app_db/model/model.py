
import cv2
import mediapipe as mp
import numpy as np
import tensorflow as tf
import keras_cv


# YOLOV8 모델 불러오기
backbone = keras_cv.models.YOLOV8Backbone.from_preset("yolo_v8_xs_backbone", include_rescaling=True)

YOLOV8_model = keras_cv.models.YOLOV8Detector(
    num_classes=1,
    bounding_box_format="xyxy",
    backbone=backbone,
    fpn_depth=5
)
YOLOV8_model.load_weights('./model/yolo_acne_detection.weights.h5')
YOLOV8_model.build(input_shape=(None, 640, 640, 3))


# 얼굴 랜드마크 감지: Mediapipe Face Mesh
mp_face_mesh = mp.solutions.face_mesh
face_mesh = mp_face_mesh.FaceMesh(static_image_mode=True, max_num_faces=1, refine_landmarks=True)

# 얼굴 부위별 랜드마크 인덱스
part_indices = {
    '이마': [8, 9, 10, 107, 66, 105, 63, 70, 71, 109, 108, 151, 296, 334, 293, 300, 299,
            383, 368, 389, 356, 337, 276, 283, 282, 295, 285, 336]
            + list(range(65, 69)),

    '코': [0, 1, 2, 5, 6, 45, 275, 274, 164, 165, 97, 98, 99,
            2, 94, 240, 218, 219, 220, 237, 218, 134,399, 398],

    '오른쪽볼': [116, 117, 118, 119, 120, 121, 128, 130, 132,
            226, 113, 225, 224, 223, 222, 221, 189, 190, 137, 139, 146],

    '왼쪽볼': [345, 346, 347, 348, 349, 350, 359, 361,
            447, 366, 436, 435, 414, 398, 397]+ list(range(380,390)),

    '턱': [0, 17, 170, 175 ,364, 335, 172, 152, 395, 396, 397,400]
}

# 얼굴 부위의 Bounding Box 계산
def get_part_bounding_box(image, landmarks, indices):
    points = np.array([
        [int(landmarks.landmark[i].x * image.shape[1]),
         int(landmarks.landmark[i].y * image.shape[0])]
        for i in indices
    ])
    x_min, y_min = points.min(axis=0)
    x_max, y_max = points.max(axis=0)
    return x_min, y_min, x_max, y_max

# 얼굴 부위 crop & resize
def crop_and_resize(image, bbox):
    x_min, y_min, x_max, y_max = bbox
    cropped = image[y_min:y_max, x_min:x_max]
    resized = cv2.resize(cropped, (640, 640))
    return resized, (x_min, y_min, x_max, y_max), cropped.shape[:2]

# 이미지 파일 로드
def load_test_image(file):

    file_bytes = file.read()
    np_arr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if img is None:
        return FileNotFoundError
    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    return img

# YOLOV8 모델로 여드름 탐지
def get_yolo_predictions(model, img, threshold=0.4): # threshold 지정
    img_tensor = tf.expand_dims(tf.cast(img, tf.float32), axis=0)
    y_pred = model.predict(img_tensor, verbose=0)

    # 예측 결과에서 bounding box, class, confidence score 가져오기
    boxes, classes, scores = y_pred["boxes"], y_pred["classes"], y_pred["confidence"]

    # 신뢰도 점수 0.4 이상이고 class_id가 0인 박스만 필터링
    filtered_boxes = [
        box for box, cls, score in zip(boxes[0], classes[0], scores[0]) if cls == 0 and score >= threshold
    ]

    return filtered_boxes

# 원본 이미지로 변환
def resize_boxes_to_original(boxes, cropped_size, orig_bbox):
    crop_h, crop_w = cropped_size
    x_min, y_min, _, _ = orig_bbox
    scale_x, scale_y = crop_w / 640, crop_h / 640

    resized_boxes = []
    for x1, y1, x2, y2 in boxes:
        resized_boxes.append([
            x_min + x1 * scale_x,
            y_min + y1 * scale_y,
            x_min + x2 * scale_x,
            y_min + y2 * scale_y
        ])
    return resized_boxes


# 여드름 부위별 탐지 결과 분석
def analyze_acne_by_parts_result(file):

    # 이미지 불러오기 및 전처리 함수
    img = load_test_image(file)

    results = face_mesh.process(img)
    if not results.multi_face_landmarks:
        print("얼굴 인식 실패")
        return img, {"error": "얼굴 인식 실패"}

    face_landmarks = results.multi_face_landmarks[0]
    part_acne_map = {part: False for part in part_indices.keys()}
    acne_boxes_by_part = {part: [] for part in part_indices.keys()}

    # 부위별 yolo 예측 실행
    for part, indices in part_indices.items():
        bbox = get_part_bounding_box(img, face_landmarks, indices)
        resized_img, orig_bbox, cropped_size = crop_and_resize(img, bbox)

        acne_boxes = get_yolo_predictions(YOLOV8_model, resized_img, threshold=0.4)  # threshold 지정
        acne_boxes = resize_boxes_to_original(acne_boxes, cropped_size, orig_bbox)

        if acne_boxes:
            part_acne_map[part] = True
            acne_boxes_by_part[part] = acne_boxes

    # 가장 여드름이 많은 부위 결정
    total_acne_count = 0
    acne_count_by_part = {}

    for part, has_acne in part_acne_map.items():
        acne_count = len(acne_boxes_by_part[part])
        total_acne_count += acne_count
        acne_count_by_part[part] = acne_count

    results_dict = {
        "total_acne_count": total_acne_count,
        "acne_count_by_part": acne_count_by_part,
    }

    if total_acne_count > 0:
        # 우선순위에 따른 부위 결정
        priority_order = ["이마", "턱", "왼쪽볼", "오른쪽볼", "코"]
        max_acne_count = max(acne_count_by_part.values())
        max_acne_part = min(
            (part for part, count in acne_count_by_part.items() if count == max_acne_count),
            key=lambda p: priority_order.index(p)
        )
        results_dict["max_acne_part"] = max_acne_part
        print(f"가장 여드름이 많은 부위: {max_acne_part}")
    else:
        results_dict["max_acne_part"] = None
        print("여드름이 탐지되지 않았습니다.")

    return img, results_dict