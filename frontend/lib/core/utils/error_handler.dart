import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

/// Unified app exception with user-friendly message.
class AppException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic original;

  AppException(this.message, {this.statusCode, this.original});

  @override
  String toString() => message;

  /// Factory from DioException — extracts backend error detail.
  factory AppException.fromDio(DioException e) {
    final statusCode = e.response?.statusCode;
    final data = e.response?.data;

    // Try extract structured error from backend
    if (data is Map) {
      final detail =
          data['detail'] ?? data['error']?['detail'] ?? data['error'];
      if (detail != null) {
        return AppException(detail.toString(),
            statusCode: statusCode, original: e);
      }
    }

    // Fallback messages by status code
    switch (statusCode) {
      case 400:
        return AppException('Invalid request. Please check your input.',
            statusCode: statusCode, original: e);
      case 401:
        return AppException('Session expired. Please sign in again.',
            statusCode: statusCode, original: e);
      case 403:
        return AppException('You do not have permission for this action.',
            statusCode: statusCode, original: e);
      case 404:
        return AppException('Resource not found.',
            statusCode: statusCode, original: e);
      case 409:
        return AppException('Conflict — this action was already performed.',
            statusCode: statusCode, original: e);
      case 422:
        return AppException('Validation error. Please check your input.',
            statusCode: statusCode, original: e);
      case 429:
        return AppException('Too many requests. Please wait a moment.',
            statusCode: statusCode, original: e);
      case 500:
        return AppException('Server error. Please try again later.',
            statusCode: statusCode, original: e);
      default:
        break;
    }

    // Network-level errors
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.sendTimeout:
      case DioExceptionType.receiveTimeout:
        return AppException(
            'Connection timed out. Check your internet connection.',
            original: e);
      case DioExceptionType.connectionError:
        return AppException(
            'Cannot reach server. Check your internet connection.',
            original: e);
      case DioExceptionType.cancel:
        return AppException('Request was cancelled.', original: e);
      default:
        return AppException(
            e.message ?? 'Something went wrong. Please try again.',
            statusCode: statusCode,
            original: e);
    }
  }

  /// Factory from any error
  factory AppException.from(dynamic e) {
    if (e is AppException) return e;
    if (e is DioException) return AppException.fromDio(e);
    return AppException(e.toString(), original: e);
  }
}

/// Helper to show error snackbar from any exception.
void showErrorSnackBar(BuildContext context, dynamic error) {
  final message =
      error is AppException ? error.message : AppException.from(error).message;
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: Colors.red.shade700,
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 4),
    ),
  );
}

/// Helper to show success snackbar.
void showSuccessSnackBar(BuildContext context, String message) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(message),
      backgroundColor: Colors.green.shade700,
      behavior: SnackBarBehavior.floating,
      duration: const Duration(seconds: 3),
    ),
  );
}
