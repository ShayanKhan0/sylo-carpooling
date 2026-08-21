// ignore_for_file: avoid_web_libraries_in_flutter, deprecated_member_use

import 'dart:typed_data';
import 'dart:html' as html;

Future<String> saveOrOpenCsv({
  required List<int> bytes,
  required String fileName,
}) async {
  final data = Uint8List.fromList(bytes);
  final blob = html.Blob([data], 'text/csv;charset=utf-8');
  final url = html.Url.createObjectUrlFromBlob(blob);

  final anchor = html.AnchorElement(href: url)
    ..setAttribute('download', fileName)
    ..style.display = 'none';

  html.document.body?.children.add(anchor);
  anchor.click();
  anchor.remove();
  html.Url.revokeObjectUrl(url);

  return fileName;
}
