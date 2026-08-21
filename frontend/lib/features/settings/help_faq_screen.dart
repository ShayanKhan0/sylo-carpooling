import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import '../../core/services/auth_service.dart';
import '../../core/services/help_faq_service.dart';
import '../shared/elite_design.dart';

class HelpFaqScreen extends StatefulWidget {
  const HelpFaqScreen({super.key});

  @override
  State<HelpFaqScreen> createState() => _HelpFaqScreenState();
}

enum _HelpTab { faq, rules }

enum _AudienceFilter { all, passenger, driver }

class _HelpFaqScreenState extends State<HelpFaqScreen> {
  final HelpFaqService _helpFaqService = HelpFaqService();

  _HelpTab _selectedTab = _HelpTab.faq;
  _AudienceFilter _selectedAudience = _AudienceFilter.all;
  List<_HelpItem> _faqItems = const [];
  List<_HelpItem> _ruleItems = const [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadContent();
  }

  Future<void> _loadContent() async {
    final role =
        (await AuthService().getUserRole() ?? 'passenger').toLowerCase();
    final data = await _helpFaqService.getHelpContent();

    if (!mounted) return;

    setState(() {
      _faqItems = _parseItems(data['faq']);
      _ruleItems = _parseItems(data['rules']);
      _selectedAudience =
          role == 'driver' ? _AudienceFilter.driver : _AudienceFilter.passenger;
      _isLoading = false;
    });
  }

  List<_HelpItem> _parseItems(dynamic rawList) {
    if (rawList is! List) return const [];
    return rawList
        .whereType<Map>()
        .map((entry) {
          final map = Map<String, dynamic>.from(entry);
          final title = (map['title'] ?? '').toString().trim();
          final body = (map['body'] ?? '').toString().trim();
          var audience = (map['audience'] ?? 'all').toString().toLowerCase();
          if (audience != 'driver' && audience != 'passenger') {
            audience = 'all';
          }
          return _HelpItem(title: title, body: body, audience: audience);
        })
        .where((item) => item.title.isNotEmpty && item.body.isNotEmpty)
        .toList(growable: false);
  }

  List<_HelpItem> get _visibleItems {
    final source = _selectedTab == _HelpTab.faq ? _faqItems : _ruleItems;
    if (_selectedAudience == _AudienceFilter.all) return source;
    final role =
        _selectedAudience == _AudienceFilter.driver ? 'driver' : 'passenger';
    return source
        .where((item) => item.audience == 'all' || item.audience == role)
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

  @override
  Widget build(BuildContext context) {
    return EliteDesign.scaffold(
      context: context,
      title: 'Help Center',
      subtitle: 'Support & community guidelines',
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
                      Text('SUPPORT', style: EliteDesign.sectionEyebrow()),
                      const SizedBox(height: 6),
                      Text(
                        _selectedTab == _HelpTab.faq
                            ? 'Questions\n& Answers'
                            : 'Community\nRules',
                        style: EliteDesign.hero(size: 34),
                      ),
                      const SizedBox(height: 10),
                      Text(
                        'Quick answers, safety rules, and role-specific guidance for riders and drivers. Tap a card to expand it.',
                        style: EliteDesign.cardBody(size: 13.5),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                _tabRow(),
                const SizedBox(height: 12),
                _audienceRow(),
                const SizedBox(height: 14),
                if (_visibleItems.isEmpty)
                  EliteDesign.panel(
                    child: Text(
                      'No help content available right now. Please check back later.',
                      style: EliteDesign.cardBody(),
                    ),
                  )
                else
                  ..._visibleItems.map(
                    (item) => Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _ExpandableHelpCard(
                        item: item,
                        audienceLabel: _audienceLabel(item.audience),
                      ),
                    ),
                  ),
              ],
            ),
    );
  }

  Widget _tabRow() {
    return Row(
      children: [
        Expanded(
          child: EliteDesign.segmentedChip(
            label: 'FAQ',
            icon: Icons.question_answer_rounded,
            selected: _selectedTab == _HelpTab.faq,
            onTap: () => setState(() => _selectedTab = _HelpTab.faq),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: EliteDesign.segmentedChip(
            label: 'RULES',
            icon: Icons.shield_rounded,
            selected: _selectedTab == _HelpTab.rules,
            onTap: () => setState(() => _selectedTab = _HelpTab.rules),
          ),
        ),
      ],
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
          selected: _selectedAudience == _AudienceFilter.all,
          onTap: () =>
              setState(() => _selectedAudience = _AudienceFilter.all),
        ),
        EliteDesign.segmentedChip(
          label: 'RIDERS',
          icon: Icons.emoji_people_rounded,
          selected: _selectedAudience == _AudienceFilter.passenger,
          onTap: () =>
              setState(() => _selectedAudience = _AudienceFilter.passenger),
        ),
        EliteDesign.segmentedChip(
          label: 'DRIVERS',
          icon: Icons.directions_car_filled_rounded,
          selected: _selectedAudience == _AudienceFilter.driver,
          onTap: () =>
              setState(() => _selectedAudience = _AudienceFilter.driver),
        ),
      ],
    );
  }
}

class _ExpandableHelpCard extends StatefulWidget {
  final _HelpItem item;
  final String audienceLabel;
  const _ExpandableHelpCard({
    required this.item,
    required this.audienceLabel,
  });

  @override
  State<_ExpandableHelpCard> createState() => _ExpandableHelpCardState();
}

class _ExpandableHelpCardState extends State<_ExpandableHelpCard>
    with SingleTickerProviderStateMixin {
  bool _open = false;

  @override
  Widget build(BuildContext context) {
    return EliteDesign.panel(
      padding: EdgeInsets.zero,
      radius: 20,
      child: Material(
        color: Colors.transparent,
        borderRadius: BorderRadius.circular(20),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: () => setState(() => _open = !_open),
          child: Padding(
            padding: const EdgeInsets.fromLTRB(18, 16, 18, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        widget.item.title,
                        style: EliteDesign.cardTitle(),
                      ),
                    ),
                    const SizedBox(width: 10),
                    EliteDesign.pill(label: widget.audienceLabel.toUpperCase()),
                    const SizedBox(width: 10),
                    AnimatedRotation(
                      turns: _open ? 0.5 : 0,
                      duration: const Duration(milliseconds: 240),
                      curve: Curves.easeOutCubic,
                      child: Icon(
                        Icons.keyboard_arrow_down_rounded,
                        size: 22,
                        color: EliteDesign.textPrimary.withValues(alpha: 0.8),
                      ),
                    ),
                  ],
                ),
                AnimatedCrossFade(
                  firstChild: const SizedBox(width: double.infinity, height: 0),
                  secondChild: Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(
                      widget.item.body,
                      style: GoogleFonts.inter(
                        fontSize: 13.5,
                        height: 1.52,
                        fontWeight: FontWeight.w500,
                        color:
                            EliteDesign.textPrimary.withValues(alpha: 0.92),
                      ),
                    ),
                  ),
                  crossFadeState: _open
                      ? CrossFadeState.showSecond
                      : CrossFadeState.showFirst,
                  duration: const Duration(milliseconds: 240),
                  sizeCurve: Curves.easeOutCubic,
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _HelpItem {
  final String title;
  final String body;
  final String audience;
  const _HelpItem({
    required this.title,
    required this.body,
    required this.audience,
  });
}
