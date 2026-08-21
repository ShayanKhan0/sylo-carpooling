import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/services/auth_service.dart';
import '../../core/services/help_faq_service.dart';
import '../shared/elite_design.dart';

class TermsOfServiceScreen extends StatefulWidget {
  const TermsOfServiceScreen({super.key});

  @override
  State<TermsOfServiceScreen> createState() => _TermsOfServiceScreenState();
}

enum _TermsAudienceFilter { all, passenger, driver }

class _TermsOfServiceScreenState extends State<TermsOfServiceScreen> {
  final HelpFaqService _service = HelpFaqService();

  _TermsAudienceFilter _selectedAudience = _TermsAudienceFilter.all;
  List<_TermsSection> _sections = const [];
  bool _isLoading = true;
  String _title = 'Terms of Service';
  String _effectiveDate = '';

  @override
  void initState() {
    super.initState();
    _loadTerms();
  }

  Future<void> _loadTerms() async {
    final role =
        (await AuthService().getUserRole() ?? 'passenger').toLowerCase();
    final data = await _service.getTermsContent();

    if (!mounted) return;

    setState(() {
      _title = (data['title'] ?? 'Terms of Service').toString();
      _effectiveDate = (data['effective_date'] ?? '').toString();
      _sections = _parseSections(data['sections']);
      _selectedAudience = role == 'driver'
          ? _TermsAudienceFilter.driver
          : _TermsAudienceFilter.passenger;
      _isLoading = false;
    });
  }

  List<_TermsSection> _parseSections(dynamic raw) {
    if (raw is! List) {
      return const [];
    }
    return raw
        .whereType<Map>()
        .map((entry) {
          final map = Map<String, dynamic>.from(entry);
          final title = (map['title'] ?? '').toString().trim();
          final body = (map['body'] ?? '').toString().trim();
          var audience = (map['audience'] ?? 'all').toString().toLowerCase();
          if (audience != 'driver' && audience != 'passenger') {
            audience = 'all';
          }
          return _TermsSection(title: title, body: body, audience: audience);
        })
        .where((s) => s.title.isNotEmpty && s.body.isNotEmpty)
        .toList(growable: false);
  }

  List<_TermsSection> get _visibleSections {
    if (_selectedAudience == _TermsAudienceFilter.all) {
      return _sections;
    }
    final role = _selectedAudience == _TermsAudienceFilter.driver
        ? 'driver'
        : 'passenger';
    return _sections
        .where((s) => s.audience == 'all' || s.audience == role)
        .toList(growable: false);
  }

  String _audienceLabel(String audience) {
    switch (audience) {
      case 'driver':
        return 'Driver';
      case 'passenger':
        return 'Rider';
      default:
        return 'Everyone';
    }
  }

  String _numberedTitle(int index, String title) {
    final cleaned = title.replaceFirst(RegExp(r'^\s*\d+[\.\)]\s*'), '').trim();
    return '${index + 1}. $cleaned';
  }

  @override
  Widget build(BuildContext context) {
    return EliteDesign.scaffold(
      context: context,
      title: 'Terms of Service',
      subtitle: _effectiveDate.isNotEmpty ? 'Effective $_effectiveDate' : null,
      body: _isLoading
          ? const Center(
              child: CircularProgressIndicator(
                strokeWidth: 2.6,
                valueColor: AlwaysStoppedAnimation<Color>(
                  EliteDesign.accentGreen,
                ),
              ),
            )
          : ListView(
              padding: const EdgeInsets.fromLTRB(16, 96, 16, 36),
              physics: const BouncingScrollPhysics(),
              children: [
                EliteDesign.panel(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('TERMS', style: EliteDesign.sectionEyebrow()),
                      const SizedBox(height: 6),
                      Text(_title, style: EliteDesign.hero(size: 34)),
                      const SizedBox(height: 10),
                      Text(
                        _effectiveDate.isEmpty
                            ? 'Please review these terms before continuing to use Sylo. They explain your rights, responsibilities, and what to expect as a member of the community.'
                            : 'Effective from $_effectiveDate. Please review these terms before continuing to use Sylo.',
                        style: EliteDesign.cardBody(size: 13.5),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _audienceRow(),
                const SizedBox(height: 14),
                if (_visibleSections.isEmpty)
                  EliteDesign.panel(
                    child: Text(
                      'No terms content available right now. Please check back later.',
                      style: EliteDesign.cardBody(),
                    ),
                  )
                else
                  ..._visibleSections.asMap().entries.map(
                    (entry) => Padding(
                      padding: const EdgeInsets.only(bottom: 12),
                      child: EliteDesign.panel(
                        padding:
                            const EdgeInsets.fromLTRB(18, 16, 18, 18),
                        radius: 20,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    _numberedTitle(entry.key, entry.value.title),
                                    style: EliteDesign.sectionTitle(),
                                  ),
                                ),
                                EliteDesign.pill(
                                  label: _audienceLabel(entry.value.audience)
                                      .toUpperCase(),
                                ),
                              ],
                            ),
                            const SizedBox(height: 12),
                            Text(
                              entry.value.body,
                              style: GoogleFonts.inter(
                                fontSize: 13.5,
                                height: 1.52,
                                fontWeight: FontWeight.w500,
                                color: EliteDesign.textPrimary
                                    .withValues(alpha: 0.92),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }

  Widget _audienceRow() {
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      children: [
        EliteDesign.segmentedChip(
          label: 'EVERYONE',
          icon: Icons.public_rounded,
          selected: _selectedAudience == _TermsAudienceFilter.all,
          onTap: () =>
              setState(() => _selectedAudience = _TermsAudienceFilter.all),
        ),
        EliteDesign.segmentedChip(
          label: 'RIDERS',
          icon: Icons.emoji_people_rounded,
          selected: _selectedAudience == _TermsAudienceFilter.passenger,
          onTap: () => setState(
              () => _selectedAudience = _TermsAudienceFilter.passenger),
        ),
        EliteDesign.segmentedChip(
          label: 'DRIVERS',
          icon: Icons.directions_car_filled_rounded,
          selected: _selectedAudience == _TermsAudienceFilter.driver,
          onTap: () => setState(
              () => _selectedAudience = _TermsAudienceFilter.driver),
        ),
      ],
    );
  }
}

class _TermsSection {
  final String title;
  final String body;
  final String audience;
  const _TermsSection({
    required this.title,
    required this.body,
    required this.audience,
  });
}
