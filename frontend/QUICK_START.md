# Sylo - Quick Start Guide

## 🎨 Color Scheme Inspiration

Based on research of modern ride-hailing apps like **InDrive** and **Yango**, here's what makes their designs work:

### InDrive Observations:
- ✨ **Bright green/lime (#00D26A)** as primary brand color
- 🎯 **High contrast** with clean white backgrounds
- 📱 **Minimal color palette** - focuses on 2-3 main colors
- 🔲 **Lots of white space** for clarity
- ⚡ **Vibrant CTAs** that pop against white

### Yango Observations:
- 🌟 **Vibrant yellow/orange** branding
- ☀️ **Warm, approachable** feel
- 🎨 **Bold color blocks** for visual hierarchy
- 🔵 **Professional** yet friendly

### Your Sylo Color Scheme:
I've created a **bright, professional navy blue & white** theme:

**Primary Colors:**
- 🔵 **Navy Blue** (#1A237E) - Main brand color
- ⚪ **Pure White** (#FFFFFF) - Background
- 🌊 **Bright Blue** (#2196F3) - Secondary
- 💎 **Vibrant Cyan** (#00BCD4) - Accent/CTAs

**Features:**
- ✅ High contrast for readability
- ✅ Bright, modern appearance
- ✅ Professional corporate feel
- ✅ Accessible color combinations

## 🚀 Getting Started

### 1. Install Dependencies

First, navigate to the frontend directory and install all dependencies:

```bash
cd "D:\Projects\Projects Inprogress\FYP\SmartCarpoolingApp\frontend"
flutter pub get
```

### 2. Download Required Fonts

Download the **Inter** font family from [Google Fonts](https://fonts.google.com/specimen/Inter) and place the following files in `assets/fonts/`:

- Inter-Regular.ttf
- Inter-Medium.ttf
- Inter-SemiBold.ttf
- Inter-Bold.ttf

### 3. Run the App

```bash
flutter run
```

## 📱 App Features

### ✨ Animated Splash Screen
- **Professional entrance animation** with fade, scale, and rotate effects
- **Pulsing logo** with glow effect
- **3-second duration** before auto-navigation
- **Checks login status** automatically

### 🔐 Sign In Screen
- **Clean, modern design** with social login options
- **Form validation** for email and password
- **Smooth animations** on page load
- **Google & Apple** sign-in placeholders

### 📊 Dashboard Screen
- **Gradient header** with personalized greeting
- **Quick action cards** for finding/offering rides
- **Recent trips** section with status badges
- **Stats cards** showing user metrics
- **Smooth scroll** with sliver app bar

## 🎯 Navigation Flow

```
Splash Screen (3s)
    ↓
Check Auth Status
    ↓
├─→ Not Logged In → Sign In Screen → Dashboard
└─→ Logged In → Dashboard
```

## 🏗️ Project Structure

```
lib/
├── core/
│   ├── theme/
│   │   ├── app_colors.dart      # Color palette
│   │   └── app_theme.dart       # Material theme config
│   ├── constants/
│   │   └── app_constants.dart   # App-wide constants
│   └── services/
│       └── auth_service.dart    # Authentication service
├── features/
│   ├── splash/
│   │   └── splash_screen.dart   # Animated splash
│   ├── auth/
│   │   └── signin_screen.dart   # Sign in page
│   └── dashboard/
│       └── dashboard_screen.dart # Main dashboard
└── main.dart                     # App entry point
```

## 🔧 Configuration

### Backend API Connection

Update the API URL in `lib/core/constants/app_constants.dart`:

```dart
static const String baseUrl = 'http://YOUR_BACKEND_URL/api/v1';
```

### Customize Colors

Edit colors in `lib/core/theme/app_colors.dart` to match your exact preferences.

### Adjust Animations

Modify animation durations in `lib/core/constants/app_constants.dart`.

## 📝 TODO: Next Steps

1. ✅ Basic app structure created
2. ✅ Splash screen with animation
3. ✅ Sign-in page with form
4. ✅ Dashboard with UI elements
5. ⬜ Implement actual backend integration
6. ⬜ Add sign-up screen
7. ⬜ Add forgot password flow
8. ⬜ Create ride finding/offering screens
9. ⬜ Add map integration
10. ⬜ Implement real-time features

## 🎨 Design Guidelines

Following the **InDrive/Yango** approach:

1. **Keep it simple** - Focus on core actions
2. **Use bright colors sparingly** - Navy blue for trust, cyan for CTAs
3. **Lots of white space** - Don't crowd the UI
4. **Clear hierarchy** - Important actions stand out
5. **Smooth animations** - Professional feel
6. **High contrast** - Easy to read in any lighting

## 💡 Tips

- The app uses **Material Design 3** for modern UI
- All colors are defined in one place for easy customization
- **SharedPreferences** handles login persistence
- Animations are smooth and performant
- Code is well-commented for easy understanding

## 🚨 Important Notes

- Download Inter fonts before running
- Set correct backend URL before testing auth
- The splash screen checks login status automatically
- All screens have entry animations for smooth UX

---

**Your backend is untouched and ready to use!** 🎉
