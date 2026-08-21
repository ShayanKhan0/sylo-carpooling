import 'csv_export_downloader_stub.dart'
    if (dart.library.html) 'csv_export_downloader_web.dart' as impl;

Future<String> saveOrOpenCsv({
  required List<int> bytes,
  required String fileName,
}) {
  return impl.saveOrOpenCsv(bytes: bytes, fileName: fileName);
}
