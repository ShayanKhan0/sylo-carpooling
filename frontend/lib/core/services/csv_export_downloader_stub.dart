import 'dart:io';

import 'package:open_filex/open_filex.dart';
import 'package:path_provider/path_provider.dart';

Future<String> saveOrOpenCsv({
  required List<int> bytes,
  required String fileName,
}) async {
  final dir = await getApplicationDocumentsDirectory();
  final path = '${dir.path}/$fileName';
  final file = File(path);
  await file.writeAsBytes(bytes, flush: true);
  await OpenFilex.open(path);
  return path;
}
