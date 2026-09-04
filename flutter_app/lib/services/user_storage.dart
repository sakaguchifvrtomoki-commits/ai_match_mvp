import 'package:shared_preferences/shared_preferences.dart';

abstract class UserStorage {
  static const String userIdKey = 'fairies_user_id';

  Future<String?> loadUserId();
  Future<void> saveUserId(String userId);
  Future<void> clearUserId();
}

class SharedPreferencesUserStorage implements UserStorage {
  const SharedPreferencesUserStorage({
    this.explicitUserId = const String.fromEnvironment('FAIRIES_USER_ID'),
  });

  final String explicitUserId;

  String? get _validExplicitUserId {
    if (explicitUserId.isEmpty || explicitUserId.length > 64) return null;
    return RegExp(r'^[a-zA-Z0-9_-]+$').hasMatch(explicitUserId)
        ? explicitUserId
        : null;
  }

  @override
  Future<String?> loadUserId() async {
    final preferences = await SharedPreferences.getInstance();
    final override = _validExplicitUserId;
    if (override != null) {
      final saved = await preferences.setString(UserStorage.userIdKey, override);
      if (!saved) {
        throw const UserStorageException('Failed to save explicit user ID.');
      }
      return override;
    }
    return preferences.getString(UserStorage.userIdKey);
  }

  @override
  Future<void> saveUserId(String userId) async {
    final preferences = await SharedPreferences.getInstance();
    final saved = await preferences.setString(UserStorage.userIdKey, userId);
    if (!saved) throw const UserStorageException('Failed to save user ID.');
  }

  @override
  Future<void> clearUserId() async {
    final preferences = await SharedPreferences.getInstance();
    final removed = await preferences.remove(UserStorage.userIdKey);
    if (!removed && preferences.containsKey(UserStorage.userIdKey)) {
      throw const UserStorageException('Failed to clear user ID.');
    }
  }
}

class UserStorageException implements Exception {
  const UserStorageException(this.message);

  final String message;
}
