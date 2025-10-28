# OCR Problem and Troubleshooting Steps

This document summarizes the ongoing OCR challenges, specifically concerning the accurate extraction of the Driving License (DL) number from rotated images, and the steps taken to address them.

## 1. The Core Problem: Inaccurate DL Number OCR from Rotated Images

**Observation:** When a rotated image of a Driving License is uploaded, the Optical Character Recognition (OCR) engine (Tesseract) consistently misreads parts of the DL number. For example, the actual DL number `KA14 20120005353` is frequently misidentified as `16814 20120006363`. While other text on the document is generally readable, this specific numerical and alphanumeric sequence is prone to errors.

**Impact:** This inaccuracy directly affects the robustness of the AI's ability to recognize and provide correct DL numbers, even with the enhanced regex post-processing in `backend/llm.py`, as the regex operates on the flawed OCR output.

## 2. Troubleshooting Steps and Outcomes

### Attempt 1: Implementing Deskewing (Rotation Correction) using Hough Line Transform

*   **Action:** Introduced a `deskew_image` function in `backend/ocr.py` that used OpenCV's Canny edge detection and Hough Line Transform to detect the skew angle and rotate the image to correct it.
*   **Initial Issue:** The `deskew_image` function included an image inversion step (`cv2.bitwise_not(gray)`) which proved detrimental.
*   **Outcome (with inversion):** OCR accuracy significantly *reduced*, producing garbled and unreadable text (e.g., `No +] : ತಿ > oie 9026012 : 1565`). This indicated a severe regression.

### Attempt 2: Fixing Deskewing (Removing Image Inversion)

*   **Action:** Removed the `cv2.bitwise_not(gray)` line from the `deskew_image` function in `backend/ocr.py` to prevent color inversion.
*   **Outcome:** While the garbled output was resolved, the OCR accuracy for the DL number did not improve. The deskewing process, even without inversion, was still not effectively correcting the rotation or was introducing other issues, leading to continued misreadings.

### Attempt 3: Reverting Deskewing (Hough Line Transform)

*   **Action:** Completely removed the `deskew_image` function and all its calls from `backend/ocr.py`.
*   **Outcome:** OCR accuracy was restored to the "less bad" state, where most text was readable, but the DL number still contained errors (e.g., `16814` instead of `KA14`). This confirmed that the deskewing logic was actively harming the OCR.

### Attempt 4: Implementing Deskewing using Min-Area Rectangle (Contour-based)

*   **Action:** Re-introduced a new `deskew_image_min_area_rect` function in `backend/ocr.py` using a different approach based on `cv2.minAreaRect` and contour detection, which is often more robust for text blocks.
*   **Outcome:** This new deskewing method also failed to improve OCR accuracy for the DL number and resulted in similar misreadings. This indicated that this deskewing approach was also not suitable for the specific image characteristics.

### Attempt 5: Reverting Deskewing (Min-Area Rectangle)

*   **Action:** Completely removed the `deskew_image_min_area_rect` function and all its calls from `backend/ocr.py`.
*   **Outcome:** OCR accuracy was restored to the "less bad" state, confirming that this deskewing attempt was also detrimental.

### Attempt 6: Adjusting Tesseract Page Segmentation Mode (PSM) to `1`

*   **Action:** Changed `tesseract_config` in `backend/ocr.py` from `r'--oem 3 --psm 3'` to `r'--oem 3 --psm 1'`. `psm 1` enables automatic page segmentation with Orientation and Script Detection (OSD).
*   **Outcome:** This change did not improve the OCR accuracy for the DL number. The misreadings persisted.

### Attempt 7: Adjusting Tesseract Page Segmentation Mode (PSM) to `11`

*   **Action:** Changed `tesseract_config` in `backend/ocr.py` from `r'--oem 3 --psm 1'` to `r'--oem 3 --psm 11'`. `psm 11` is for "sparse text," often suitable for ID cards or non-uniform text layouts.
*   **Outcome:** (Pending user feedback)

## 3. Current Status and Recommendations

The application currently uses Tesseract with `psm 11` and includes denoising and adaptive binarization. The `backend/llm.py` has enhanced regex for post-processing DL numbers.

Despite multiple attempts to improve OCR accuracy for rotated images through automated deskewing and Tesseract PSM adjustments, the DL number is still consistently misread. This suggests that the current image pre-processing and Tesseract configuration are struggling with the inherent challenges of the rotated image.

**Recommendations for Improved OCR:**

1.  **Manual Image Rotation (Strongly Recommended):** The most reliable way to achieve accurate OCR from rotated documents is to ensure they are in an upright, correct orientation *before* uploading them to the system. This bypasses the complexities and potential inaccuracies of automated deskewing.
2.  **Further Tesseract Tuning (Advanced):**
    *   Experiment with other `psm` values (e.g., `psm 6` for a single uniform block).
    *   Consider `oem` (OCR Engine Mode) options if Tesseract 5.x is installed, though `oem 3` (default, LSTM + Legacy) is generally robust.
3.  **Custom Tesseract Training (Long-term/Advanced):** For highly specific document types or fonts that Tesseract struggles with, creating custom training data for Tesseract can significantly improve accuracy. This is a complex and time-consuming process.
4.  **Alternative OCR Engines (Long-term/Advanced):** Exploring other OCR libraries or cloud-based OCR services might offer better performance for challenging images, but would require significant integration effort.

For immediate and reliable improvement, **manually rotating images to the correct orientation before upload is the most practical and effective solution.**

## 8. Irrelevant Text on English-Only Images

**Observation:** When processing images that contain only English text, the OCR output includes irrelevant characters. This suggests that the multi-language detection (`eng+kan1+hin`) is causing interference, with Tesseract misinterpreting some English characters as Kannada or Hindi.

**Action:** To resolve this, the OCR process will be modified to use only the English language model (`lang='eng'`) when processing documents. This will prevent interference from the other language models and is expected to produce cleaner output for English-only text.

## 9. Final Optimal Configuration

After extensive testing, the optimal Tesseract configuration for this application has been determined to be **`--oem 3 --psm 6`**.

*   **`--oem 3` (Default Engine):** This mode, which uses both the legacy and LSTM engines, provided the most reliable results across all three languages, especially when paired with the new trained data files.
*   **`--psm 6` (Assume a single uniform block of text):** This Page Segmentation Mode proved to be the most effective at correctly interpreting the layout of the ID card documents.

This combination provides the best balance of accuracy and reliability for English, Kannada, and Hindi text within this application.
