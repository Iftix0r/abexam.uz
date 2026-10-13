import 'dart:io';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:package_info_plus/package_info_plus.dart';

/// Phone model, OS and app version — sent at sign-in so the admin panel
/// shows which device each session belongs to.
Future<Map<String, String>> deviceInfo() async {
  var device = '', platform = '', version = '';
  try {
    final info = DeviceInfoPlugin();
    if (Platform.isAndroid) {
      final a = await info.androidInfo;
      device = '${a.manufacturer[0].toUpperCase()}${a.manufacturer.substring(1)} ${a.model}';
      platform = 'Android ${a.version.release}';
    } else if (Platform.isIOS) {
      final i = await info.iosInfo;
      device = i.utsname.machine;
      platform = 'iOS ${i.systemVersion}';
    }
  } catch (_) {}
  try {
    final p = await PackageInfo.fromPlatform();
    version = '${p.version}+${p.buildNumber}';
  } catch (_) {}
  return {'device': device.isEmpty ? 'mobile' : device, 'platform': platform, 'app_version': version};
}
