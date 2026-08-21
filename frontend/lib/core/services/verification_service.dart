import 'package:image_picker/image_picker.dart';
import 'package:dio/dio.dart';
import 'api_client.dart';

class VerificationService {
  final ApiClient _api = ApiClient();

  /// POST /verification/upload  multipart form upload for AI verification
  /// [documentType]: cnic, driving_license, vehicle_registration, selfie, insurance
  /// [imageFile]: a real XFile from image_picker
  Future<Map<String, dynamic>> uploadDocument({
    required String documentType,
    required XFile imageFile,
  }) async {
    final formData = FormData.fromMap({
      'doc_type': documentType,
      'file': MultipartFile.fromBytes(
        await imageFile.readAsBytes(),
        filename: imageFile.name,
      ),
    });
    final res = await _api.post('/verification/upload', data: formData);
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// DELETE /verification/document/{docType}  delete uploaded document image(s)
  Future<Map<String, dynamic>> deleteDocument({
    required String documentType,
  }) async {
    final res = await _api.delete('/verification/document/$documentType');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// GET /verification/status/{userId}  get verification status
  Future<Map<String, dynamic>> getStatus(String userId) async {
    final res = await _api.get('/verification/status/$userId');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// POST /verification/identity-data/verify/{docType}
  /// Runs Google OCR-based identity data match using the already uploaded image.
  Future<Map<String, dynamic>> verifyIdentityData({
    required String documentType,
  }) async {
    final res =
        await _api.post('/verification/identity-data/verify/$documentType');
    return Map<String, dynamic>.from(unwrap(res));
  }

  /// POST /verification/selfie/reverify-intent
  /// Driver-only action to replace selfie and re-enter verification flow.
  Future<Map<String, dynamic>> startDriverSelfieReverification() async {
    final res = await _api.post('/verification/selfie/reverify-intent');
    return Map<String, dynamic>.from(unwrap(res));
  }
}
