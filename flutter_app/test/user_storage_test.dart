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

  test('explicit historical ID replaces and persists over a stored ID', () async {
    SharedPreferences.setMockInitialValues({
      UserStorage.userIdKey: 'user_previous_test',
    });
    const storage = SharedPreferencesUserStorage(
      explicitUserId: 'user_historical_master',
    );

    expect(await storage.loadUserId(), 'user_historical_master');

    final preferences = await SharedPreferences.getInstance();
    expect(
      preferences.getString(UserStorage.userIdKey),
      'user_historical_master',
    );
    expect(
      await const SharedPreferencesUserStorage().loadUserId(),
      'user_historical_master',
    );
  });

  test('absent or invalid override preserves normal stored-ID behavior', () async {
    SharedPreferences.setMockInitialValues({
      UserStorage.userIdKey: 'user_existing',
    });

    expect(
      await const SharedPreferencesUserStorage().loadUserId(),
      'user_existing',
    );
    expect(
      await const SharedPreferencesUserStorage(
        explicitUserId: 'invalid/user',
      ).loadUserId(),
      'user_existing',
    );
  });
}
