import 'package:dio/dio.dart';

import 'api_client.dart';

class HelpFaqService {
  final ApiClient _apiClient = ApiClient();

  Future<Map<String, dynamic>> getHelpContent() async {
    try {
      final response = await _apiClient.get('/help/content');
      final payload = unwrap(response);
      if (payload is Map<String, dynamic>) {
        return payload;
      }
    } on DioException {
      // Use local fallback content if backend is unavailable.
    }
    return _fallbackContent;
  }

  Future<Map<String, dynamic>> getTermsContent() async {
    try {
      final response = await _apiClient.get('/help/terms');
      final payload = unwrap(response);
      if (payload is Map<String, dynamic>) {
        return payload;
      }
    } on DioException {
      // Use local fallback content if backend is unavailable.
    }
    return _fallbackTermsContent;
  }

  Future<Map<String, dynamic>> getPrivacyContent() async {
    try {
      final response = await _apiClient.get('/help/privacy');
      final payload = unwrap(response);
      if (payload is Map<String, dynamic>) {
        return payload;
      }
    } on DioException {
      // Use local fallback content if backend is unavailable.
    }
    return _fallbackPrivacyContent;
  }

  static const Map<String, dynamic> _fallbackContent = {
    'faq': [
      {
        'audience': 'all',
        'title': 'What is Sylo Smart Carpooling?',
        'body':
            'Sylo helps students and office users share rides safely, reduce travel cost, and commute with verified profiles.'
      },
      {
        'audience': 'all',
        'title': 'How does ride matching work?',
        'body':
            'Sylo matches users using route direction, pickup and drop points, seat availability, and selected time preferences.'
      },
      {
        'audience': 'all',
        'title': 'How does wallet payment work?',
        'body':
            'You can top up your wallet and use it for ride payments. Driver earnings are credited to wallet and can be requested as payout.'
      },
      {
        'audience': 'all',
        'title': 'What should I do in an emergency?',
        'body':
            'Use the in-app SOS option immediately and contact local emergency services when needed.'
      },
      {
        'audience': 'passenger',
        'title': 'How do I book a ride?',
        'body':
            'Open available rides, pick a suitable option, confirm seats, and submit your booking request.'
      },
      {
        'audience': 'passenger',
        'title': 'Can I cancel a booking?',
        'body':
            'Yes. You can cancel before ride start. Repeated last-minute cancellations may reduce account trust.'
      },
      {
        'audience': 'driver',
        'title': 'How do I become a driver?',
        'body':
            'Complete driver onboarding with license and identity documents, then wait for verification approval.'
      },
      {
        'audience': 'driver',
        'title': 'How do payouts work?',
        'body':
            'Payout requests are processed only from available wallet balance. Requests above balance are blocked in-app.'
      },
    ],
    'rules': [
      {
        'audience': 'all',
        'title': 'Respect and professional behavior',
        'body':
            'Harassment, abuse, threats, hate speech, and discrimination are not allowed on Sylo.'
      },
      {
        'audience': 'all',
        'title': 'No illegal activity',
        'body':
            'Weapons, drugs, illegal items, and unlawful acts are strictly prohibited during rides.'
      },
      {
        'audience': 'all',
        'title': 'Use real account details',
        'body':
            'Keep your profile information accurate. Fraud, fake bookings, and impersonation can lead to suspension.'
      },
      {
        'audience': 'passenger',
        'title': 'Be ready at pickup',
        'body':
            'Arrive on time and confirm pickup and drop details before trip start.'
      },
      {
        'audience': 'passenger',
        'title': 'Maintain vehicle etiquette',
        'body':
            'Use seatbelt, keep the vehicle clean, and avoid behavior that distracts the driver.'
      },
      {
        'audience': 'driver',
        'title': 'Follow traffic and safety laws',
        'body':
            'Always obey road laws, drive responsibly, and never exceed available seat capacity.'
      },
      {
        'audience': 'driver',
        'title': 'Keep documents and vehicle data valid',
        'body':
            'License, verification records, and vehicle details must remain valid and up to date.'
      },
      {
        'audience': 'driver',
        'title': 'Zero tolerance for intoxicated driving',
        'body':
            'Driving under influence or reckless behavior results in immediate account action.'
      },
    ],
  };

  static const Map<String, dynamic> _fallbackTermsContent = {
    'version': '2026-04-08',
    'title': 'Sylo Terms of Service',
    'effective_date': '2026-04-08',
    'sections': [
      {
        'audience': 'all',
        'title': '1. Acceptance of Terms',
        'body':
            'By creating an account or using Sylo, you agree to these terms. If you do not agree, do not use the platform.'
      },
      {
        'audience': 'all',
        'title': '2. Eligibility and Account',
        'body':
            'You must provide accurate information and keep your account secure. Sylo may require identity or driver verification for some features.'
      },
      {
        'audience': 'all',
        'title': '3. Service Scope',
        'body':
            'Sylo provides smart carpooling for students and office communities. Riders can book rides and verified drivers can publish rides.'
      },
      {
        'audience': 'all',
        'title': '4. Payments and Wallet',
        'body':
            'Wallet transactions and payouts are subject to available balance, applicable limits, and platform checks.'
      },
      {
        'audience': 'all',
        'title': '5. Prohibited Conduct',
        'body':
            'Harassment, abuse, discrimination, fraud, impersonation, illegal items, and unlawful activity are strictly prohibited.'
      },
      {
        'audience': 'passenger',
        'title': '6. Rider Responsibilities',
        'body':
            'Riders must be punctual, confirm trip details, follow safety rules, and respect driver and vehicle etiquette.'
      },
      {
        'audience': 'driver',
        'title': '7. Driver Responsibilities',
        'body':
            'Drivers must keep documents and vehicle details valid, obey traffic laws, and maintain safe conduct during all rides.'
      },
      {
        'audience': 'driver',
        'title': '8. Safety Compliance',
        'body':
            'Intoxicated driving, reckless behavior, and seat-capacity violations are zero-tolerance breaches and may trigger immediate account action.'
      },
      {
        'audience': 'all',
        'title': '9. Enforcement and Suspension',
        'body':
            'Sylo may investigate reports and suspend or terminate accounts that breach safety, verification, or platform integrity requirements.'
      },
      {
        'audience': 'all',
        'title': '10. Privacy and Data Use',
        'body':
            'Sylo uses account, location, and ride data to operate matching, tracking, payments, and safety functions within policy limits.'
      },
      {
        'audience': 'all',
        'title': '11. Service Changes',
        'body':
            'Sylo may update features and terms over time. Continued use after updates indicates acceptance of revised terms.'
      },
      {
        'audience': 'all',
        'title': '12. Contact and Governing Law',
        'body':
            'For support or legal questions, use official in-app support channels. These terms are governed by applicable laws of Pakistan.'
      },
    ],
  };

  static const Map<String, dynamic> _fallbackPrivacyContent = {
    'version': '2026-04-08',
    'title': 'Sylo Privacy Policy',
    'effective_date': '2026-04-08',
    'sections': [
      {
        'audience': 'all',
        'title': '1. Introduction',
        'body':
            'Sylo protects personal data for riders and drivers and explains what information is collected and how it is used.'
      },
      {
        'audience': 'all',
        'title': '2. Data We Collect',
        'body':
            'Sylo may collect account details, trip data, wallet activity, device diagnostics, and support communication records.'
      },
      {
        'audience': 'all',
        'title': '3. Location Data',
        'body':
            'Location is used for matching, navigation, pickup and drop accuracy, live tracking, and ride safety features.'
      },
      {
        'audience': 'all',
        'title': '4. How Data Is Used',
        'body':
            'Data is used to operate accounts, process rides and payments, improve reliability, and detect fraud or safety risks.'
      },
      {
        'audience': 'all',
        'title': '5. Data Sharing',
        'body':
            'Sylo shares only necessary trip details between matched users and may use trusted service providers under confidentiality controls.'
      },
      {
        'audience': 'all',
        'title': '6. Data Retention and Security',
        'body':
            'Sylo retains data as needed for operations, compliance, dispute handling, and safety. Technical and organizational safeguards apply.'
      },
      {
        'audience': 'passenger',
        'title': '7. Rider Privacy Notes',
        'body':
            'Riders share only trip-relevant details with matched drivers and should avoid posting sensitive personal data in ride chats.'
      },
      {
        'audience': 'driver',
        'title': '8. Driver Privacy Notes',
        'body':
            'Drivers may provide additional verification and vehicle records. Matched riders see only details needed for safe trip coordination.'
      },
      {
        'audience': 'all',
        'title': '9. User Controls and Rights',
        'body':
            'Users can update profile details in-app and request account actions through official support channels, subject to legal obligations.'
      },
      {
        'audience': 'all',
        'title': '10. Policy Updates',
        'body':
            'Sylo may update this policy. Changes are reflected by an updated effective date and may be announced in-app.'
      },
      {
        'audience': 'all',
        'title': '11. Contact',
        'body':
            'For privacy concerns or requests, contact support through official in-app channels.'
      },
    ],
  };
}
