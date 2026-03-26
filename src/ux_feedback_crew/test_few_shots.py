from dotenv import load_dotenv
load_dotenv()

from src.ux_feedback_crew.tools.feedback_tool_fewshot import generate_feedback_fewshot


def main():
    vision = """
│  {"screen_type": "E-commerce Home Screen / Product Discovery / Deals Page", "components": [{"name": "Status Bar", "type": "System UI", "description": "Standard iOS status bar displaying time, network, and       │
│  battery indicators."}, {"name": "Header Navigation", "type": "Navigation Bar", "elements": [{"name": "Search Icon", "icon": "magnifying glass"}, {"name": "App Logo", "text": "TEMU"}], "description": "Top       │
│  fixed bar with search functionality and app branding."}, {"name": "Security/Trust Banner", "type": "Information Banner", "elements": [{"name": "Checkmark Icon", "icon": "checked"}, {"name": "Security Text",    │
│  "text": "Safe payment | Security privacy | Purchase protection"}, {"name": "Arrow Icon", "icon": "right arrow"}], "description": "A banner communicating trust and security features, likely tappable for more    │
│  details."}, {"name": "Promotional Card: Free Shipping", "type": "Deal Card", "elements": [{"name": "Truck Icon", "icon": "shipping truck"}, {"name": "Offer Text", "text": "Free shipping"}, {"name": "Countdown  │
│  Label", "text": "Ends in"}, {"name": "Countdown Timer", "value": "20 : 26 : 18", "unit": "hours:minutes:seconds"}], "description": "A card highlighting a free shipping offer with a visible countdown timer."},  │
│  {"name": "Promotional Card: 30% Off", "type": "Deal Card", "elements": [{"name": "Tag Icon", "icon": "price tag"}, {"name": "Offer Text", "text": "30% off"}, {"name": "Condition Text", "text": "On first 3      │
│  orders"}], "description": "A card promoting a 30% discount specifically for the first three orders."}, {"name": "User Review Card", "type": "Testimonial", "elements": [{"name": "User Name", "text": "D***s"},   │
│  {"name": "Star Rating", "value": "5 stars"}, {"name": "Review Text", "text": "material is great . was my first time ordering fro..."}, {"name": "Image Indicator Icon", "icon": "image"}], "description": "A      │
│  compact card displaying a positive user review, suggesting authenticity with a partial name and image indicator."}, {"name": "Section Header: New user gift", "type": "Section Title", "elements": [{"name":      │
│  "Title Text", "text": "New user gift"}, {"name": "Arrow Icon", "icon": "right arrow"}], "description": "A header for a section targeting new users, indicating more content is available."}, {"name": "New User   │
│  Gift Deal Card", "type": "Coupon/Offer", "elements": [{"name": "Discount Percentage", "text": "30%"}, {"name": "Discount Scope", "text": "OFF SITELWIDE"}, {"name": "Call to Action Button", "text": "GET         │
│  ALL"}], "description": "A prominent coupon-style card offering a sitewide discount for new users."}, {"name": "New User Gift Product Carousel", "type": "Horizontal Scroll Product List", "items": [{"name":      │
│  "Product Card 1", "image": "blue shirt", "current_price": "$0.90", "original_price": "$6.99"}, {"name": "Product Card 2", "image": "kids outfit", "current_price": "$0.43", "original_price": "$12.99"},          │
│  {"name": "Product Card 3", "image": "partially visible", "current_price": "$0.3X"}], "description": "A horizontally scrollable list of products, likely heavily discounted items for new users."}, {"name":       │
│  "Section Header: Lightning deals", "type": "Section Title with Timer", "elements": [{"name": "Lightning Bolt Icon", "icon": "lightning bolt"}, {"name": "Title Text", "text": "Lightning deals"}, {"name":        │
│  "Arrow Icon", "icon": "right arrow"}, {"name": "Countdown Label", "text": "Ends in"}, {"name": "Countdown Timer", "value": "20 : 26 : 18", "unit": "hours:minutes:seconds"}], "description": "A section header    │
│  for time-sensitive 'Lightning deals', featuring an icon and a countdown."}, {"name": "Lightning Deals Product Carousel", "type": "Horizontal Scroll Product List", "items": [{"name": "Product Card 1", "image":  │
│  "black puffer jacket", "current_price": "$33.98", "items_sold": "3 sold"}, {"name": "Product Card 2", "image": "white sneakers", "current_price": "$17.89", "items_sold": "56 sold"}, {"name": "Product Card 3",  │
│  "image": "beaded bracelets", "current_price": "$0.48", "items_sold": "3,849 sold"}], "description": "A horizontally scrollable list of products with current prices and units sold, indicating popularity and     │
│  urgency."}, {"name": "Christmas Banner", "type": "Promotional Banner", "elements": [{"name": "Background Image", "image": "Christmas themed"}, {"name": "Text", "text": "Christmas"}], "description": "A large    │
│  banner promoting Christmas-themed products or sales."}, {"name": "Bottom Navigation Bar", "type": "Persistent Navigation", "elements": [{"name": "Home", "icon": "filled house", "status": "active"}, {"name":    │
│  "Categories", "icon": "equalizer/filter"}, {"name": "You", "icon": "person"}, {"name": "Cart", "icon": "shopping cart", "additional_info": "20:26:18 | Free shipping", "progress_bar": true}], "description": "A  │
│  fixed bottom navigation bar allowing users to quickly switch between main app sections, with an active 'Home' indicator and a cart timer."}], "layout_structure": "The screen features a fixed top header         │
│  (status bar and app logo/search) and a fixed bottom navigation bar. The main content area is vertically scrollable and structured into distinct, vertically stacked sections. Within these sections, product      │
│  listings are organized into horizontal carousels. Key promotional elements are presented as card-based banners, creating a modular and scannable interface.", "color_scheme": {"primary_accents": {"orange":      │
│  "Used for app logo, discount percentages (30% OFF, GET ALL button), and a promotional card background.", "green": "Used for the 'Cart' section's countdown timer and progress bar in the bottom navigation."},    │
│  "neutrals": {"white": "Predominant background color for the screen, cards, and bottom navigation.", "black": "Used for most primary text, icons, and countdown timer numbers.", "light_grey": "Background for     │
│  security banner, free shipping card, countdown timer backgrounds, and crossed-out prices.", "dark_grey": "Used for 'Ends in' text and 'sold' counts for secondary information."}, "seasonal": {"red_gold_green":  │
│  "Prominent in the 'Christmas' banner."}}, "typography": {"font_family": "Sans-serif (likely system default like SF Pro for iOS)", "weights": {"bold": "Used for app logo, main deal percentages (e.g., '30%       │
│  OFF'), 'Free shipping', and current product prices.", "regular": "Used for most body text, secondary information, and labels."}, "sizes": {"large": "App logo, main deal percentages.", "medium": "Section        │
│  headers, primary text in banners, current prices.", "small": "Secondary information like 'Ends in', 'sold' counts, crossed-out prices, bottom navigation labels."}, "case": "Mostly sentence case, with 'TEMU',   │
│  'OFF SITELWIDE', and 'GET ALL' using all caps for emphasis."}, "spacing_and_density": {"vertical_spacing": "Generous vertical spacing between major sections (e.g., promotional cards, review, product            │
│  carousels) to ensure clear separation.", "horizontal_spacing": "Moderate padding between items within horizontal carousels, allowing individual product cards to breathe.", "padding_within_components":          │
│  "Adequate internal padding within cards and banners for readability. Countdown timers are visually compact.", "overall_density": "The screen is information-dense, aiming to showcase many deals and products.    │
│  However, the use of distinct sections and horizontal scrolling helps manage visual clutter."}, "accessibility_observations": ["Good contrast between most text and background colors (e.g., black on white/grey,  │
│  orange on white).", "Interactive elements like buttons and banners appear to have sufficient tap target sizes.", "Clear visual hierarchy is established through font sizes, weights, and color, guiding user      │
│  attention to important information like prices and deals.", "Small text used for 'sold' counts and crossed-out prices might be challenging for users with visual impairments.", "Standard and widely              │
│  recognizable icons are used, aiding comprehension.", "Color is used to emphasize deals (orange) and urgency (green for cart timer), but is usually accompanied by text labels, which is good for colorblind       │
│  users."], "notable_patterns": ["Persistent Bottom Navigation: Provides consistent access to main app sections.", "Horizontal Product Carousels: Efficiently displays a large number of products in a limited      │
│  vertical space, ideal for browsing deals.", "Countdown Timers: Creates a sense of urgency and encourages immediate action, a common e-commerce tactic.", "Trust Signals: 'Safe payment | Security privacy |       │
│  Purchase protection' banner builds user confidence.", "Promotional Card/Banner Design: Visually distinct cards highlight various offers (free shipping, percentage off).", "Social Proof: User review and 'X      │
│  sold' indicators leverage peer influence to encourage purchases.", "First-time User Incentive: Dedicated section/offer for new users to drive acquisition.", "Seasonal/Themed Banners: 'Christmas' banner aligns  │
│  with current events or holidays, enhancing relevance.", "Price Comparison: Displaying original prices crossed out next to discounted prices emphasizes savings.", "Card-based Layout: Organizes diverse content   │
│  into digestible, visually distinct modules."]}              
""".strip()

    heuristics = """
│  {"violations": [{"id": 10, "name": "Help and documentation", "description": "The UI analysis does not provide any indication of accessible help features, onboarding tutorials, tooltips, or readily available    │
│  documentation for users. While a home screen might not require extensive inline help, the absence of any mention suggests a potential gap in supporting users, especially new ones or those needing               │
│  clarification on specific features.", "severity": "medium"}, {"id": 7, "name": "Flexibility and efficiency of use", "description": "While horizontal carousels are efficient for displaying products, the         │
│  analysis does not mention any specific shortcuts, advanced features, or customizable options designed to speed up interaction for expert users. The design seems optimized for general browsing, but lacks        │
│  explicit elements to cater to varying levels of user proficiency beyond basic navigation.", "severity": "low"}], "strengths": [{"id": 1, "name": "Visibility of system status", "description": "The presence of   │
│  'Countdown Timers' for deals is an excellent example of keeping users informed about the status of time-sensitive offers, creating urgency and transparency. This provides clear feedback on what is going on     │
│  with promotional elements.", "severity": "high"}, {"id": 2, "name": "Match between system and real world", "description": "The use of 'Standard and widely recognizable icons' and the context of an 'E-commerce  │
│  Home Screen / Product Discovery / Deals Page' strongly suggest that the language, concepts (deals, coupons, categories), and visual metaphors used align with users' real-world expectations and mental models    │
│  for online shopping.", "severity": "high"}, {"id": 4, "name": "Consistency and standards", "description": "Multiple patterns indicate strong consistency: 'Persistent Bottom Navigation' ensures consistent       │
│  access, 'Card-based Layout' provides a uniform structure, 'Clear visual hierarchy' is maintained, and 'Standard and widely recognizable icons' are used. Consistent color usage for emphasis (orange for deals,   │
│  green for timers) further reinforces this.", "severity": "high"}, {"id": 6, "name": "Recognition rather than recall", "description": "The UI minimizes memory load through several patterns: 'Persistent Bottom   │
│  Navigation' keeps main sections visible, 'Horizontal Product Carousels' display numerous products without requiring users to recall options, 'Promotional Card/Banner Design' makes offers easily recognizable,   │
│  and 'Price Comparison' (crossed-out original prices) directly shows savings without requiring recall.", "severity": "high"}, {"id": 8, "name": "Aesthetic and minimalist design", "description": "The             │
│  'Card-based Layout' organizes diverse content into 'digestible, visually distinct modules', contributing to a clean and scannable interface. 'Clear visual hierarchy' through font sizes, weights, and color,     │
│  along with strategic use of space (implied by the modular design), helps avoid clutter and guides user attention effectively.", "severity": "high"}], "overall_score": 4, "summary": "The mobile UI for this      │
│  e-commerce home screen demonstrates strong adherence to many core usability heuristics. It excels in providing a highly recognizable, consistent, and aesthetically pleasing interface that minimizes cognitive   │
│  load for users. Key strengths include clear system status feedback (countdown timers), familiar design patterns and iconography, strong visual consistency across elements, and an efficient layout that          │
│  promotes recognition over recall, such as displaying discounted prices and using card-based modules. These elements collectively make the product discovery and deal browsing experience intuitive and            │
│  organized. \n\nAreas for potential improvement primarily stem from a lack of information in the analysis rather than explicit flaws. There's no clear evidence of dedicated features for error prevention, user   │
│  control (beyond basic navigation), or comprehensive help and documentation. While some of these might be less critical for a home screen, their absence could impact the overall user experience on other parts   │
│  of the application or for users needing specific guidance. Introducing specific shortcuts or advanced filtering options could also enhance flexibility for expert users. Overall, the design provides a solid     │
│  foundation for a user-friendly e-commerce experience."}                                                                                                                                                           │
│                                                             
""".strip()

    result = generate_feedback_fewshot.run(
        vision_analysis=vision,
        heuristic_evaluation=heuristics,
        evaluation_id="fewshot_test"
    )

    print("\n===== FEW-SHOT RESULT =====\n")
    print(result)


if __name__ == "__main__":
    main()