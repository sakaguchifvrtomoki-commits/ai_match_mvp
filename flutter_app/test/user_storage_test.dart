import 'package:fairies_app/services/user_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  setUp(() => SharedPreferences.setMockInitialValues({}));

  test('stores, loads and clears only the Fairies user ID', () async {
    const storage = SharedPreferencesUserStorage();

    expect(await storage.loadUserId(), isNull);
    await storage.saveUserId('user_saved');
    expect(await storage.loadUserId(), 'user_saved');
    await storage.clearUserId();
    expect(await storage.loadUserId(), isNull);
  });
}
