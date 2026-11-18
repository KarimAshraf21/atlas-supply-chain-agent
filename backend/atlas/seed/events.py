"""Synthetic risk events (fictional, but modelled on real-world risk patterns)."""

from __future__ import annotations

from dataclasses import dataclass, field

# (target_id, impact, magnitude 0-1, added_days)
Affect = tuple[str, str, float, int | None]


@dataclass(frozen=True)
class EventSpec:
    id: str
    title: str
    title_ar: str
    type: str
    severity: int
    probability: float
    status: str
    start_offset: int  # days relative to AS_OF
    duration_days: int
    summary: str
    affects: list[Affect]
    detail: str = ""
    arabic_article: str = ""
    mentions: list[str] = field(default_factory=list)


RISK_EVENTS: list[EventSpec] = [
    EventSpec(
        "RE-REDSEA",
        "Renewed attacks on merchant shipping close Bab el-Mandeb to most container lines",
        "هجمات جديدة على السفن التجارية تغلق مضيق باب المندب أمام معظم خطوط الحاويات",
        "conflict",
        5,
        1.0,
        "active",
        -21,
        60,
        "Major carriers suspended Red Sea transits after a series of drone and missile strikes near Bab el-Mandeb. "
        "Asia–Europe and Asia–Red Sea services are diverting around the Cape of Good Hope.",
        [("BAB_EL_MANDEB", "closure", 0.85, 14)],
        detail="War-risk insurance premiums have risen to 0.7% of hull value and spot rates on Asia–Mediterranean "
        "lanes have jumped 140% in three weeks. Carriers say diversions will last at least until mid-January.",
        arabic_article=(
            "علّقت كبرى شركات الشحن مرور سفنها عبر البحر الأحمر بعد سلسلة من الهجمات بالطائرات المسيّرة والصواريخ "
            "قرب مضيق باب المندب. وتتجه الخدمات بين آسيا وأوروبا وموانئ البحر الأحمر حول رأس الرجاء الصالح، ما يضيف "
            "نحو أسبوعين إلى زمن الرحلة. وارتفعت أسعار الشحن الفوري على خطوط آسيا–المتوسط بنسبة 140% خلال ثلاثة أسابيع، "
            "فيما يتوقع الناقلون استمرار التحويلات حتى منتصف يناير على الأقل."
        ),
        mentions=["BAB_EL_MANDEB", "CAPE", "EGSOK", "SAJED", "LP-ORIENT", "LP-CAPEEX"],
    ),
    EventSpec(
        "RE-SUEZ",
        "Suez Canal convoys slowed as security measures tighten",
        "تباطؤ القوافل في قناة السويس مع تشديد الإجراءات الأمنية",
        "geopolitical",
        3,
        1.0,
        "active",
        -16,
        30,
        "Reduced northbound and southbound convoys add waiting time at both canal entrances.",
        [("SUEZ", "delay", 0.3, 3)],
        detail="Average waiting time at the southern anchorage has risen from 11 to 70 hours; the canal authority "
        "has offered rebates to carriers that keep their Suez rotations.",
        arabic_article=(
            "أدى تقليص عدد القوافل في الاتجاهين إلى زيادة فترات الانتظار عند مدخلي قناة السويس. وارتفع متوسط زمن "
            "الانتظار في منطقة المخطاف الجنوبية من 11 ساعة إلى نحو 70 ساعة، بينما عرضت هيئة القناة خصومات للناقلين "
            "الذين يحافظون على رحلاتهم عبر القناة."
        ),
        mentions=["SUEZ", "EGPSD", "EGSOK"],
    ),
    EventSpec(
        "RE-TYPHOON",
        "Super typhoon forecast to make landfall near Kaohsiung",
        "توقعات بوصول إعصار فائق إلى اليابسة قرب كاوشيونغ",
        "weather",
        4,
        0.6,
        "forecast",
        6,
        6,
        "Meteorologists expect a category-4 typhoon to hit southern Taiwan; port and fab shutdowns are likely.",
        [
            ("TWKHH", "closure", 0.9, 6),
            ("TAIWAN_STRAIT", "delay", 0.4, 2),
            ("SUP-FORMOSIC", "capacity_reduction", 0.3, None),
        ],
        detail="Kaohsiung port has issued a level-2 alert. Semiconductor plants in the southern science park "
        "typically halt production for 2–4 days during typhoon landfall.",
        mentions=["TWKHH", "SUP-FORMOSIC", "SUP-TAMSUI", "CMP-SICMOS"],
    ),
    EventSpec(
        "RE-SHANGHAI",
        "Container backlog builds at Shanghai after fog and yard-system outage",
        "تكدس الحاويات في شنغهاي بعد الضباب وتعطل نظام الساحات",
        "infrastructure",
        2,
        1.0,
        "active",
        -5,
        12,
        "Vessel waiting times at Shanghai have doubled; export bookings are rolling by up to a week.",
        [("CNSHA", "delay", 0.3, 5)],
        detail="Yard utilisation passed 92% after a two-day terminal operating system outage coincided with dense fog.",
        mentions=["CNSHA", "SUP-BOXWORKS", "SUP-TIANSHAN"],
    ),
    EventSpec(
        "RE-GRAPHITE",
        "China tightens export licensing for battery-grade graphite",
        "الصين تشدد تراخيص تصدير الجرافيت المستخدم في البطاريات",
        "regulatory",
        4,
        1.0,
        "active",
        -48,
        180,
        "New end-user licensing requirements have slowed graphite anode exports by an estimated 40%.",
        [("MAT-GRAPHITE", "capacity_reduction", 0.4, None), ("SUP-HEILONG", "capacity_reduction", 0.4, None)],
        detail="Licences now take 45 working days and require end-use declarations. Cell makers outside China report "
        "inventories of anode material falling below six weeks.",
        mentions=["MAT-GRAPHITE", "SUP-HEILONG", "SUP-ZHENGYUAN", "SUP-MEKONG", "CN"],
    ),
    EventSpec(
        "RE-GALLIUM",
        "Gallium export ban extended to additional destinations",
        "توسيع حظر تصدير الغاليوم ليشمل وجهات إضافية",
        "regulatory",
        4,
        1.0,
        "active",
        -30,
        365,
        "Restrictions on gallium exports tighten supply for microcontroller and power-device makers.",
        [("MAT-GALLIUM", "capacity_reduction", 0.6, None), ("SUP-YUNNANGA", "capacity_reduction", 0.6, None)],
        detail="Spot gallium prices outside China rose 55% in a month; chipmakers are drawing down safety stocks.",
        mentions=["MAT-GALLIUM", "SUP-YUNNANGA", "SUP-TAMSUI", "SUP-PENANG", "CMP-MCU"],
    ),
    EventSpec(
        "RE-RTMSTRIKE",
        "Dockworkers at Rotterdam vote on 7-day strike",
        "عمال الموانئ في روتردام يصوتون على إضراب لمدة 7 أيام",
        "labor_strike",
        3,
        0.4,
        "forecast",
        17,
        7,
        "A strike ballot covering lashing crews could halt container handling at Europe's largest port.",
        [("NLRTM", "closure", 0.7, 7)],
        detail="Unions are demanding inflation-linked pay and automation guarantees; talks resume on 1 December.",
        mentions=["NLRTM", "WH-ROTTERDAM", "CUS-POLDER", "CUS-ZONNEKRACHT"],
    ),
    EventSpec(
        "RE-DAEGU",
        "Daegu Copper Foil enters creditor-led restructuring talks",
        "شركة دايغو لرقائق النحاس تدخل مفاوضات إعادة هيكلة بقيادة الدائنين",
        "financial",
        4,
        0.35,
        "forecast",
        10,
        90,
        "Lenders to the copper-foil maker are weighing a debt-for-equity swap after covenant breaches.",
        [("SUP-DAEGU", "insolvency", 0.9, None)],
        detail="The company supplies 6 µm copper foil to several Asian LFP cell makers and has no second plant.",
        mentions=["SUP-DAEGU", "MAT-CUFOIL", "SUP-ZHENGYUAN", "SUP-MEKONG"],
    ),
    EventSpec(
        "RE-MEKONGCYBER",
        "Ransomware attack disrupts Mekong Power Cells' production systems",
        "هجوم فدية يعطل أنظمة الإنتاج في ميكونغ باور سيلز",
        "cyber",
        3,
        1.0,
        "active",
        -6,
        14,
        "The Vietnamese cell maker is running two of four lines manually while systems are restored.",
        [("SUP-MEKONG", "capacity_reduction", 0.5, None)],
        detail="The company says customer data was not affected and expects full output within two weeks.",
        mentions=["SUP-MEKONG", "CMP-LFPCELL", "VN"],
    ),
    EventSpec(
        "RE-EGGRID",
        "Egypt extends industrial load-shedding schedule",
        "مصر تمدد جدول تخفيف الأحمال للمصانع",
        "infrastructure",
        2,
        1.0,
        "active",
        -17,
        30,
        "Industrial zones face rolling two-hour power cuts while gas supplies to power plants are constrained.",
        [("FAC-SOKHNA", "capacity_reduction", 0.15, None), ("FAC-10RAM", "capacity_reduction", 0.1, None)],
        detail="Factories with on-site generation are exempt from the second daily cut.",
        arabic_article=(
            "تواجه المناطق الصناعية انقطاعات دورية للكهرباء لمدة ساعتين يوميًا في ظل محدودية إمدادات الغاز لمحطات "
            "التوليد. وتُعفى المصانع التي تمتلك محطات توليد ذاتية من فترة الانقطاع الثانية. ويشمل الجدول المنطقة "
            "الاقتصادية لقناة السويس ومدينة العاشر من رمضان."
        ),
        mentions=["FAC-SOKHNA", "FAC-10RAM", "EG"],
    ),
    EventSpec(
        "RE-HORMUZ",
        "Naval tensions raise risk of Strait of Hormuz disruption",
        "التوترات البحرية ترفع مخاطر تعطل الملاحة في مضيق هرمز",
        "geopolitical",
        5,
        0.2,
        "forecast",
        20,
        21,
        "Analysts put a one-in-five chance on a multi-week disruption to Gulf container traffic.",
        [("HORMUZ", "closure", 0.8, 10)],
        detail="A closure would cut off Jebel Ali and Dammam from sea freight; overland routes from Red Sea ports "
        "add 4–6 days.",
        arabic_article=(
            "يقدّر محللون احتمال تعطل حركة الحاويات في الخليج لعدة أسابيع بنحو واحد من خمسة. ومن شأن أي إغلاق أن يعزل "
            "ميناءي جبل علي والدمام عن الشحن البحري، بينما تضيف الطرق البرية من موانئ البحر الأحمر ما بين أربعة "
            "وستة أيام."
        ),
        mentions=["HORMUZ", "AEJEA", "SADMM", "CUS-NAJD", "CUS-EMIRATESGRID"],
    ),
    EventSpec(
        "RE-PANAMA",
        "Panama Canal draft restrictions return amid low lake levels",
        "عودة قيود الغاطس في قناة بنما بسبب انخفاض منسوب البحيرة",
        "weather",
        2,
        1.0,
        "active",
        -12,
        45,
        "Lower maximum drafts reduce slots for neopanamax vessels.",
        [("PANAMA", "delay", 0.25, 4)],
        mentions=["PANAMA", "CLSAI", "SUP-ATACAMACU", "SUP-SALARLI"],
    ),
    EventSpec(
        "RE-CHILELI",
        "Chile proposes higher lithium royalties in mining reform",
        "تشيلي تقترح رفع رسوم الليثيوم ضمن إصلاحات التعدين",
        "regulatory",
        2,
        0.5,
        "forecast",
        45,
        365,
        "A draft bill would raise royalties on lithium brine operations.",
        [("SUP-SALARLI", "price_increase", 0.15, None), ("MAT-LI2CO3", "price_increase", 0.1, None)],
        mentions=["SUP-SALARLI", "MAT-LI2CO3", "CL"],
    ),
    EventSpec(
        "RE-UFLPA",
        "US customs detains solar shipments over polysilicon traceability",
        "الجمارك الأمريكية تحتجز شحنات طاقة شمسية بسبب تتبع البولي سيليكون",
        "regulatory",
        3,
        1.0,
        "active",
        -25,
        120,
        "Importers must prove polysilicon origin; shipments linked to flagged suppliers are being held.",
        [("SUP-JUNGGAR", "capacity_reduction", 0.3, None), ("SUP-TIANSHAN", "capacity_reduction", 0.2, None)],
        mentions=["SUP-JUNGGAR", "SUP-TIANSHAN", "MAT-POLYSI", "PRD-SOLKIT", "US"],
    ),
    EventSpec(
        "RE-SHENGHUA",
        "Shenghua Magnetics fails customer quality audit",
        "شنغهوا للمغناطيسيات تفشل في تدقيق الجودة",
        "financial",
        2,
        1.0,
        "active",
        -9,
        60,
        "Corrective actions on winding defects are cutting usable output by about a quarter.",
        [("SUP-SHENGHUA", "capacity_reduction", 0.25, None)],
        mentions=["SUP-SHENGHUA", "CMP-INDUCTOR"],
    ),
    EventSpec(
        "RE-PENANGFLOOD",
        "Penang flooding halts semiconductor assembly lines",
        "فيضانات بينانغ توقف خطوط تجميع أشباه الموصلات",
        "weather",
        3,
        1.0,
        "resolved",
        -69,
        9,
        "Flooding shut several back-end assembly plants for over a week.",
        [("SUP-PENANG", "capacity_reduction", 0.6, None)],
        mentions=["SUP-PENANG", "MY"],
    ),
    EventSpec(
        "RE-TWQUAKE",
        "Magnitude 6.4 earthquake briefly halts Taiwanese fabs",
        "زلزال بقوة 6.4 يوقف مصانع الرقائق التايوانية لفترة وجيزة",
        "weather",
        3,
        1.0,
        "resolved",
        -98,
        4,
        "Fabs evacuated staff and recalibrated tools; most production resumed within four days.",
        [("SUP-FORMOSIC", "capacity_reduction", 0.2, None), ("SUP-TAMSUI", "capacity_reduction", 0.15, None)],
        mentions=["SUP-FORMOSIC", "SUP-TAMSUI", "TW"],
    ),
]
