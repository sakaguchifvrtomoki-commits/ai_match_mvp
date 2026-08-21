import 'package:flutter/material.dart';

import 'screens/home_screen.dart';

void main() {
  runApp(const FairiesApp());
}

class FairiesApp extends StatelessWidget {
  const FairiesApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'フェアリーズ',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
      home: const HomeScreen(),
    );
  }
}
