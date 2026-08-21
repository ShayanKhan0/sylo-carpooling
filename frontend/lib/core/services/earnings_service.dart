import 'dart:convert';
import 'dart:typed_data';
import 'package:dio/dio.dart';
import '../models/earnings_model.dart';
import 'api_client.dart';
import 'csv_export_downloader.dart';

class EarningsService {
  final ApiClient _api = ApiClient();

  /// GET /earnings/monthly
  Future<MonthlyEarnings> getMonthly({int? year, int? month}) async {
    final nowLocal = DateTime.now();
    final targetYear = year ?? nowLocal.year;
    final targetMonth = month ?? nowLocal.month;

    final res = await _api.get('/earnings/monthly', queryParameters: {
      'year': targetYear,
      'month': targetMonth,
      '_ts': DateTime.now().millisecondsSinceEpoch,
    });
    final payload = Map<String, dynamic>.from(unwrap(res) as Map);
    return MonthlyEarnings.fromJson(payload);
  }

  /// GET /earnings/lifetime
  Future<LifetimeEarnings> getLifetime() async {
    final res = await _api.get('/earnings/lifetime', queryParameters: {
      '_ts': DateTime.now().millisecondsSinceEpoch,
    });
    final payload = Map<String, dynamic>.from(unwrap(res) as Map);
    return LifetimeEarnings.fromJson(payload);
  }

  /// GET /earnings/chart?days=30
  Future<EarningsChart> getChart({int days = 30}) async {
    final res = await _api.get('/earnings/chart', queryParameters: {
      'days': days,
      '_ts': DateTime.now().millisecondsSinceEpoch,
    });
    final payload = Map<String, dynamic>.from(unwrap(res) as Map);
    return EarningsChart.fromJson(payload);
  }

  /// GET /earnings/export/csv — downloads CSV and opens/saves it
  Future<String> exportCsv({
    String? fromDate,
    String? toDate,
    String? payoutStatus,
  }) async {
    final res = await _api.get(
      '/earnings/export/csv',
      queryParameters: {
        if (fromDate != null) 'from_date': fromDate,
        if (toDate != null) 'to_date': toDate,
        if (payoutStatus != null) 'payout_status': payoutStatus,
      },
      options: Options(responseType: ResponseType.bytes),
    );

    final bytes = _extractCsvBytes(res.data);
    final csvBytes = bytes.isEmpty ? _blankEarningsCsvBytes() : bytes;
    final fileName = _extractFilename(res) ??
        'earnings_${DateTime.now().millisecondsSinceEpoch}.csv';

    return saveOrOpenCsv(bytes: csvBytes, fileName: fileName);
  }

  List<int> _extractCsvBytes(dynamic data) {
    if (data == null) return <int>[];
    if (data is Uint8List) return data;
    if (data is List<int>) return data;
    if (data is List) return data.map((e) => e as int).toList();
    if (data is String) return utf8.encode(data);
    throw Exception('Unexpected CSV response type: ${data.runtimeType}');
  }

  List<int> _blankEarningsCsvBytes() {
    const header =
        'Ride ID,Date,From Location,To Location,Seats Booked,Earnings (PKR),Payout Status\n';
    return utf8.encode(header);
  }

  String? _extractFilename(Response res) {
    final raw = res.headers.value('content-disposition');
    if (raw == null || raw.isEmpty) return null;

    final utf8Match = RegExp(r"filename\*=UTF-8''([^;]+)", caseSensitive: false)
        .firstMatch(raw);
    if (utf8Match != null) {
      return Uri.decodeComponent(utf8Match.group(1)!);
    }

    final basicMatch =
        RegExp(r'filename="?([^";]+)"?', caseSensitive: false).firstMatch(raw);
    return basicMatch?.group(1);
  }
}
