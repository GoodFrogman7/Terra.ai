"""
Healthcare KB Synthetic Data Generator
Generates markdown files for general health and wellness knowledge base
"""
import os
from pathlib import Path
from typing import List, Tuple

class HealthcareKBGenerator:
    """Generate synthetic healthcare KB content."""
    
    def __init__(self, output_dir: str = "data/kb_healthcare"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_qa_file(self, filename: str, topic: str, qa_pairs: List[Tuple[str, str]]):
        """Generate a Q&A format markdown file."""
        content = f"# {topic}\n\n"
        for q, a in qa_pairs:
            content += f"## {q}\n\n{a}\n\n"
        
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"[HEALTHCARE KB] Generated: {filename}")
    
    def generate_article(self, filename: str, title: str, sections: List[Tuple[str, str]]):
        """Generate a longer informational article."""
        content = f"# {title}\n\n"
        for section_title, section_content in sections:
            content += f"## {section_title}\n\n{section_content}\n\n"
        
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"[HEALTHCARE KB] Generated: {filename}")
    
    def generate_all(self):
        """Generate complete healthcare KB."""
        print("[HEALTHCARE KB] Generating healthcare knowledge base...")
        
        # 1. Common Symptoms and Home Remedies
        self.generate_qa_file("health_common_symptoms.md", "Common Symptoms and Home Remedies", [
            ("What should I do for a common cold?", 
             "Rest, stay hydrated (8-10 glasses of water daily), use a humidifier, gargle warm salt water for sore throat, and take over-the-counter pain relievers like acetaminophen or ibuprofen for discomfort. Most colds resolve in 7-10 days. See a doctor if symptoms worsen or last more than 2 weeks."),
            ("How do I treat a mild headache?", 
             "Try these approaches: drink water (dehydration causes headaches), rest in a quiet, dark room, apply a cold compress to your forehead, massage temples and neck, and take over-the-counter pain relievers. If headaches are severe, frequent, or accompanied by vision changes, see a doctor."),
            ("What are remedies for indigestion?", 
             "Avoid trigger foods (spicy, fatty, acidic), eat smaller meals, don't lie down for 2-3 hours after eating, stay upright, chew food slowly, and avoid tight clothing around the waist. Over-the-counter antacids can help. If symptoms persist, consult a doctor—it could be GERD or ulcers."),
            ("How can I relieve back pain at home?", 
             "Apply ice for the first 48 hours (reduces inflammation), then switch to heat (relaxes muscles). Do gentle stretches, avoid prolonged sitting, maintain good posture, and take over-the-counter anti-inflammatories. Most back pain improves in a few weeks. See a doctor if pain radiates down legs, causes weakness, or follows an injury."),
        ])
        
        # 2. Preventive Care and Wellness
        self.generate_article("health_preventive_care.md", "Preventive Care and Wellness", [
            ("Why Preventive Care Matters", 
             "Preventive care helps detect health issues early when they're most treatable. Regular check-ups, screenings, and vaccinations can prevent diseases or catch them in early stages, saving lives and reducing healthcare costs long-term."),
            ("Recommended Health Screenings by Age", 
             "Ages 20-30: Blood pressure, cholesterol (if at risk), STI testing, skin checks. Ages 30-40: Add diabetes screening, cervical cancer screening (Pap smear every 3 years). Ages 40-50: Add mammograms (women), colorectal cancer screening (starting at 45). Ages 50+: Annual wellness visits, bone density (women 65+), prostate screening (men), lung cancer screening (smokers). Frequency varies by personal and family health history."),
            ("Essential Vaccinations for Adults", 
             "Annual flu shot, Tdap booster every 10 years (tetanus, diphtheria, pertussis), shingles vaccine (50+), pneumonia vaccine (65+ or high-risk), COVID-19 vaccines and boosters, HPV vaccine (up to age 26, sometimes 45). Consult your doctor for personalized recommendations based on health conditions and travel plans."),
            ("The Importance of Dental Check-ups", 
             "Visit the dentist every 6 months for cleanings and exams. Oral health affects overall health—gum disease is linked to heart disease, diabetes, and stroke. Regular cleanings prevent cavities, gum disease, and tooth loss. Don't skip dental care even if teeth feel fine."),
        ])
        
        # 3. Nutrition and Fitness Basics
        self.generate_article("health_nutrition_fitness.md", "Nutrition and Fitness Basics", [
            ("Building a Balanced Diet", 
             "Focus on whole foods: vegetables (fill half your plate), lean proteins (chicken, fish, beans, tofu), whole grains (brown rice, quinoa, oats), healthy fats (avocado, nuts, olive oil), and fruits. Limit processed foods, added sugars, and excessive salt. Stay hydrated with 8-10 cups of water daily."),
            ("Understanding Macronutrients", 
             "Carbohydrates provide energy (45-65% of calories)—choose complex carbs like whole grains and vegetables. Proteins build and repair tissues (10-35% of calories)—aim for 0.8g per kg of body weight. Fats support cell function and vitamin absorption (20-35% of calories)—prioritize unsaturated fats from plants, fish, and nuts."),
            ("How Much Exercise Do I Need?", 
             "Adults need 150 minutes of moderate aerobic activity (brisk walking, cycling) or 75 minutes of vigorous activity (running, swimming) per week, plus strength training 2+ days per week. Break it into 30-minute sessions, 5 days a week. Any movement is better than none—start small and build gradually."),
            ("Exercise for Beginners", 
             "Start with walking 10-15 minutes daily and gradually increase duration and intensity. Add bodyweight exercises (squats, push-ups, planks) 2x per week. Listen to your body—rest when needed. Consistency matters more than intensity. Consider working with a trainer or physical therapist if you have health concerns."),
            ("Hydration and Its Importance", 
             "Water regulates body temperature, transports nutrients, removes waste, and cushions joints. Aim for 8-10 cups daily, more if exercising or in hot weather. Signs of dehydration: dark urine, fatigue, dizziness, dry mouth. Don't wait until you're thirsty—drink regularly throughout the day."),
        ])
        
        # 4. Mental Health Basics
        self.generate_qa_file("health_mental_health.md", "Mental Health Basics", [
            ("What are signs of anxiety or depression?", 
             "Anxiety signs: Excessive worry, restlessness, rapid heartbeat, difficulty concentrating, sleep problems, panic attacks. Depression signs: Persistent sadness, loss of interest in activities, fatigue, changes in appetite/sleep, difficulty concentrating, feelings of worthlessness, thoughts of self-harm. If symptoms persist for 2+ weeks or interfere with daily life, seek professional help."),
            ("How can I manage stress effectively?", 
             "Practice deep breathing exercises, maintain regular sleep schedule (7-9 hours), exercise regularly, limit caffeine and alcohol, connect with friends/family, set boundaries at work, take breaks, engage in hobbies, try meditation or yoga, and consider therapy if stress feels overwhelming. Identify and address stress sources when possible."),
            ("When should I see a mental health professional?", 
             "Seek help if you experience: persistent sadness or anxiety lasting weeks, thoughts of self-harm or suicide, difficulty functioning at work/school/home, substance abuse, trauma from disturbing events, relationship problems, or if friends/family express concern. Early intervention improves outcomes. Therapy isn't just for crises—it's also for personal growth."),
            ("What's the difference between a therapist, psychologist, and psychiatrist?", 
             "Therapist/Counselor: Provides talk therapy, has a master's degree (LCSW, LMFT, LPC). Psychologist: Provides therapy and psychological testing, has a doctoral degree (PhD or PsyD), cannot prescribe medication. Psychiatrist: Medical doctor (MD or DO) who can prescribe medication and provide therapy, specializes in mental health conditions. Choose based on your needs."),
        ])
        
        # 5. Medication Management
        self.generate_qa_file("health_medication_management.md", "Medication Management", [
            ("How should I take medications safely?", 
             "Follow prescribed dosages and schedules exactly, take with or without food as directed, don't skip doses, finish antibiotic courses completely (even if feeling better), store medications properly (cool, dry place), check expiration dates, and never share prescriptions. Use pill organizers for multiple medications."),
            ("What questions should I ask my doctor about new medications?", 
             "Ask: What is this medication for? How and when do I take it? How long until it works? What side effects should I expect? What should I do if I miss a dose? Are there foods, drinks, or other medications to avoid? What if it doesn't work? Are there alternatives? How much does it cost?"),
            ("How do I manage multiple medications?", 
             "Keep an updated medication list (names, dosages, schedule, prescribing doctors), use pill organizers with day/time compartments, set phone alarms for doses, use medication tracking apps, have one pharmacy for all prescriptions (they'll check for interactions), and schedule regular medication reviews with your doctor or pharmacist."),
            ("What should I know about generic vs. brand-name medications?", 
             "Generic medications contain the same active ingredients as brand-name drugs and must meet the same FDA safety and effectiveness standards. They're typically 80-85% cheaper because they don't have brand development costs. Inactive ingredients (fillers, dyes) may differ but rarely cause issues. Generics are safe and effective—ask your doctor or pharmacist if switching is appropriate."),
        ])
        
        # 6. When to See a Doctor
        self.generate_article("health_when_to_see_doctor.md", "When to See a Doctor", [
            ("Emergency Symptoms (Call 911)", 
             "Seek immediate emergency care for: Chest pain or pressure, difficulty breathing, sudden severe headache (worst of your life), sudden weakness or numbness (especially one-sided), slurred speech or confusion, loss of consciousness, severe bleeding, serious burns, suspected poisoning, suicidal thoughts with a plan, severe allergic reactions (throat swelling, difficulty breathing)."),
            ("Symptoms Requiring Same-Day or Next-Day Doctor Visit", 
             "Schedule a prompt appointment for: High fever (>103°F) or fever lasting 3+ days, severe pain (abdominal, back, or elsewhere), persistent vomiting or diarrhea (especially with dehydration signs), new or worsening respiratory symptoms, unexplained weight loss, severe headache with fever/stiff neck, injuries that may need stitches, animal or human bites, eye injuries or sudden vision changes."),
            ("Symptoms to Monitor and Schedule a Routine Appointment", 
             "See your doctor within a week or two for: Persistent cough lasting 3+ weeks, minor skin rashes or changes, mild to moderate pain not improving with over-the-counter meds, fatigue lasting several weeks, mood changes (anxiety, depression), sleep problems, digestive issues, new lumps or bumps, changes in urination, or any symptom that concerns you."),
            ("How to Prepare for Doctor Appointments", 
             "Write down symptoms (when they started, severity, what makes them better/worse), list current medications and supplements, bring medical records if seeing a new doctor, prepare questions, bring a family member or friend if discussing complex issues, and be honest about lifestyle habits. Use the appointment time effectively."),
        ])
        
        # 7. Health Insurance Navigation
        self.generate_qa_file("health_insurance_basics.md", "Understanding Health Insurance", [
            ("What are the key health insurance terms I should know?", 
             "Premium: Monthly cost for coverage. Deductible: Amount you pay before insurance kicks in (e.g., $1,500). Copay: Fixed amount for visits/services (e.g., $30 per doctor visit). Coinsurance: Percentage you pay after meeting deductible (e.g., 20%). Out-of-pocket maximum: Most you'll pay annually ($9,100 in 2024 for individuals). In-network: Providers with negotiated rates (lower costs). Out-of-network: Higher costs or not covered."),
            ("How do I choose between health insurance plans?", 
             "Compare: Monthly premiums, deductibles, copays, out-of-pocket maximums, provider networks (are your doctors in-network?), prescription drug coverage, and estimated annual healthcare costs. If you're healthy and rarely need care, a high-deductible plan with lower premiums may work. If you have ongoing medical needs, pay more for a plan with lower deductibles and copays."),
            ("What is the difference between HMO, PPO, and EPO plans?", 
             "HMO (Health Maintenance Organization): Lower costs, requires primary care doctor referrals for specialists, limited to in-network providers. PPO (Preferred Provider Organization): Higher costs, more flexibility, no referrals needed, can see out-of-network providers (at higher cost). EPO (Exclusive Provider Organization): Mid-range costs, no referrals, must stay in-network except emergencies. Choose based on flexibility needs and budget."),
            ("When is open enrollment and can I get insurance outside of it?", 
             "Open enrollment is typically November 1 - January 15 for marketplace plans. You can enroll or change plans outside this period if you have a qualifying life event: job loss, marriage, divorce, birth/adoption, moving to a new state, losing other coverage. Medicaid and CHIP enroll year-round. Check Healthcare.gov or your employer benefits."),
        ])
        
        # 8. Chronic Condition Management
        self.generate_article("health_chronic_conditions.md", "Managing Chronic Health Conditions", [
            ("What are Chronic Conditions?", 
             "Chronic conditions are long-lasting health issues (lasting a year or more) requiring ongoing medical attention. Common examples: diabetes, high blood pressure, asthma, arthritis, heart disease, COPD, chronic kidney disease. They can often be managed effectively with medications, lifestyle changes, and regular monitoring."),
            ("Living with Diabetes", 
             "Monitor blood sugar regularly as prescribed, take medications consistently, follow a balanced diet (focus on complex carbs, fiber, lean proteins, limit simple sugars), exercise regularly (improves insulin sensitivity), maintain healthy weight, have regular A1C tests (every 3-6 months), check feet daily for injuries, schedule annual eye exams, and work closely with your healthcare team."),
            ("Managing High Blood Pressure", 
             "Take prescribed medications daily, monitor blood pressure at home, reduce sodium intake (<2,300mg daily, ideally <1,500mg), maintain healthy weight, exercise regularly (30 minutes most days), limit alcohol, quit smoking, manage stress, and eat a diet rich in fruits, vegetables, whole grains, and lean proteins (DASH diet)."),
            ("Asthma Management", 
             "Use controller medications daily (even when feeling well), carry rescue inhaler always, identify and avoid triggers (allergens, smoke, cold air, exercise), monitor peak flow readings, have an asthma action plan, get flu and pneumonia vaccines, and see your doctor regularly to adjust treatment. Don't ignore worsening symptoms."),
            ("Importance of Medication Adherence", 
             "Taking medications as prescribed is crucial for managing chronic conditions and preventing complications. Set reminders, use pill organizers, understand why each medication is necessary, ask about side effects and how to manage them, discuss cost concerns with your doctor (generic options, assistance programs), and never stop medications without consulting your doctor."),
        ])
        
        print(f"[HEALTHCARE KB] Generated {len(list(self.output_dir.glob('*.md')))} files in {self.output_dir}")


def main():
    """Main entry point for generating healthcare KB."""
    generator = HealthcareKBGenerator()
    generator.generate_all()
    print("[HEALTHCARE KB] Healthcare knowledge base generation complete!")


if __name__ == "__main__":
    main()

