class SessionEndResponse {
  const SessionEndResponse({required this.status});

  factory SessionEndResponse.fromJson(Map<String, dynamic> json) {
    final status = json['status'];
    if (status is! String || status != 'completed') {
      throw const FormatException('Invalid session end response.');
    }
    return SessionEndResponse(status: status);
  }

  final String status;
}
