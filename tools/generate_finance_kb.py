"""
Finance KB Synthetic Data Generator
Generates markdown files for personal finance knowledge base
"""
import os
from pathlib import Path
from typing import List, Tuple

class FinanceKBGenerator:
    """Generate synthetic finance KB content."""
    
    def __init__(self, output_dir: str = "data/kb_finance"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_qa_file(self, filename: str, topic: str, qa_pairs: List[Tuple[str, str]]):
        """Generate a Q&A format markdown file."""
        content = f"# {topic}\n\n"
        for q, a in qa_pairs:
            content += f"## {q}\n\n{a}\n\n"
        
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"[FINANCE KB] Generated: {filename}")
    
    def generate_article(self, filename: str, title: str, sections: List[Tuple[str, str]]):
        """Generate a longer informational article."""
        content = f"# {title}\n\n"
        for section_title, section_content in sections:
            content += f"## {section_title}\n\n{section_content}\n\n"
        
        filepath = self.output_dir / filename
        filepath.write_text(content, encoding="utf-8")
        print(f"[FINANCE KB] Generated: {filename}")
    
    def generate_all(self):
        """Generate complete finance KB."""
        print("[FINANCE KB] Generating finance knowledge base...")
        
        # 1. Budgeting Basics
        self.generate_article("finance_budgeting_basics.md", "Budgeting Basics", [
            ("What is a Budget?", 
             "A budget is a financial plan that helps you track income and expenses. It ensures you spend within your means and save for future goals. Creating a budget involves listing all income sources, categorizing expenses, and monitoring spending regularly."),
            ("The 50/30/20 Rule", 
             "This popular budgeting method suggests allocating 50% of after-tax income to needs (housing, food, utilities), 30% to wants (entertainment, dining out), and 20% to savings and debt repayment. Adjust these percentages based on your personal situation."),
            ("How to Create Your First Budget", 
             "Start by tracking all income and expenses for one month. Categorize spending into needs, wants, and savings. Use budgeting apps like Mint, YNAB, or spreadsheets to organize data. Review monthly and adjust categories as needed."),
            ("Common Budgeting Mistakes", 
             "Avoid underestimating expenses, forgetting irregular costs (annual insurance, gifts), being too restrictive (leading to burnout), and not tracking actual spending. Be realistic and flexible with your budget."),
        ])
        
        # 2. Saving Strategies
        self.generate_qa_file("finance_saving_strategies.md", "Saving Strategies", [
            ("How much should I save each month?", 
             "Financial experts recommend saving at least 20% of your after-tax income. Start with whatever you can afford, even if it's just $50/month, and gradually increase. Build an emergency fund of 3-6 months of expenses first, then focus on other goals."),
            ("What is the best way to automate savings?", 
             "Set up automatic transfers from checking to savings accounts right after payday. Use employer-sponsored retirement plans with automatic deductions. Many banks offer 'round-up' features that save spare change from purchases."),
            ("Where should I keep my emergency fund?", 
             "Keep emergency funds in high-yield savings accounts that offer easy access without penalties. Look for accounts with competitive interest rates (currently 4-5% APY). Avoid keeping it in checking accounts or investments that fluctuate in value."),
            ("How can I save money on a tight budget?", 
             "Cut unnecessary subscriptions, meal prep instead of eating out, use coupons and cashback apps, negotiate bills (cable, insurance), buy generic brands, and limit impulse purchases by using the 24-hour rule before buying non-essentials."),
        ])
        
        # 3. Investment Fundamentals
        self.generate_article("finance_investment_basics.md", "Investment Fundamentals", [
            ("Why Invest?", 
             "Investing helps your money grow faster than inflation, building wealth over time. Savings accounts offer safety but low returns (3-5% annually). Investments like stocks historically return 8-10% annually over long periods, though with more risk."),
            ("Understanding Stocks", 
             "Stocks represent ownership in companies. When companies grow and profit, stock values increase. You can earn returns through price appreciation and dividends. Individual stocks are riskier; diversification reduces risk."),
            ("What are Index Funds and ETFs?", 
             "Index funds and ETFs (Exchange-Traded Funds) are collections of stocks that track market indexes like the S&P 500. They offer instant diversification, low fees (0.03-0.20% expense ratios), and historically strong returns. Great for beginners."),
            ("Bonds Explained", 
             "Bonds are loans you give to governments or corporations in exchange for regular interest payments. They're safer than stocks but offer lower returns (3-5% typically). Good for diversification and income in retirement."),
            ("Risk vs. Return", 
             "Higher potential returns come with higher risk. Stocks are volatile but offer growth. Bonds are stable but slower growth. Diversify across asset types based on your age, goals, and risk tolerance. Younger investors can handle more risk."),
        ])
        
        # 4. Credit and Debt Management
        self.generate_qa_file("finance_credit_debt.md", "Credit and Debt Management", [
            ("How does credit score work?", 
             "Credit scores (300-850) measure creditworthiness. Factors: payment history (35%), credit utilization (30%), credit history length (15%), new credit (10%), credit mix (10%). Scores above 700 are good, above 800 excellent. Check free at AnnualCreditReport.com."),
            ("What is credit utilization and why does it matter?", 
             "Credit utilization is the percentage of available credit you're using. Keep it below 30% (ideally under 10%) on each card. High utilization hurts credit scores. Pay balances in full monthly or make mid-cycle payments to lower utilization."),
            ("Should I pay off debt or invest?", 
             "Pay off high-interest debt (credit cards >15% APR) before investing. For low-interest debt (mortgages, student loans <5%), consider investing while making minimum payments. Match employer 401(k) contributions first—it's free money."),
            ("What's the best debt repayment strategy?", 
             "Two popular methods: (1) Avalanche method—pay off highest interest debt first, saving more money. (2) Snowball method—pay off smallest balances first for psychological wins. Choose based on what motivates you."),
        ])
        
        # 5. Retirement Planning
        self.generate_article("finance_retirement_planning.md", "Retirement Planning", [
            ("When Should I Start Saving for Retirement?", 
             "Start as early as possible. Thanks to compound interest, someone who invests $200/month from age 25-35 (just 10 years) will have more at 65 than someone who invests $200/month from age 35-65 (30 years). Time is your greatest asset."),
            ("Understanding 401(k) Plans", 
             "401(k)s are employer-sponsored retirement accounts. Contributions are pre-tax, reducing current taxable income. Many employers match contributions (typically 3-6%)—always contribute enough to get the full match. Money grows tax-deferred until withdrawal."),
            ("Traditional IRA vs. Roth IRA", 
             "Traditional IRA: Contributions may be tax-deductible now; pay taxes on withdrawals in retirement. Best if you expect lower tax rates in retirement. Roth IRA: Contributions with after-tax dollars; withdrawals are tax-free. Best if you expect higher future tax rates. 2024 contribution limit: $7,000 ($8,000 if 50+)."),
            ("How Much Do I Need to Retire?", 
             "A common rule: save 25x your annual retirement expenses. If you need $40,000/year, save $1 million. Another approach: aim to replace 70-80% of pre-retirement income. Use retirement calculators to estimate based on current age, savings, and expected returns."),
            ("Social Security Basics", 
             "Social Security provides retirement income based on your lifetime earnings. You can claim as early as 62 (reduced benefits) or delay until 70 (increased benefits). Full retirement age is 67 for those born after 1960. Check your estimate at SSA.gov."),
        ])
        
        # 6. Tax Filing Tips
        self.generate_qa_file("finance_tax_tips.md", "Tax Filing Tips", [
            ("When are taxes due?", 
             "Federal tax returns are due April 15 each year (or the next business day if April 15 falls on a weekend/holiday). You can file for a 6-month extension until October 15, but any taxes owed must still be paid by April 15 to avoid penalties."),
            ("What are tax deductions vs. tax credits?", 
             "Deductions reduce your taxable income (e.g., $1,000 deduction saves $220 if you're in the 22% tax bracket). Credits reduce your tax bill dollar-for-dollar (e.g., $1,000 credit saves $1,000). Credits are more valuable."),
            ("Should I take the standard deduction or itemize?", 
             "For 2024, the standard deduction is $14,600 (single) or $29,200 (married filing jointly). Itemize only if deductions (mortgage interest, state taxes, charitable donations, medical expenses) exceed the standard deduction. Most people take the standard deduction."),
            ("What documents do I need to file taxes?", 
             "Gather W-2s (employment income), 1099s (freelance/investment income), receipts for deductible expenses, mortgage interest statements (1098), student loan interest statements, and records of charitable donations. Keep copies for at least 3 years."),
        ])
        
        # 7. Emergency Funds
        self.generate_article("finance_emergency_fund.md", "Emergency Funds", [
            ("What is an Emergency Fund?", 
             "An emergency fund is money set aside for unexpected expenses like job loss, medical bills, car repairs, or home emergencies. It prevents you from going into debt when life throws curveballs."),
            ("How Much Should I Save?", 
             "Most experts recommend 3-6 months of essential expenses (rent, utilities, food, minimum debt payments). If you have irregular income (freelancers, commission-based jobs) or are the sole earner, aim for 6-12 months. Start with $1,000 as a mini emergency fund."),
            ("Where to Keep Your Emergency Fund", 
             "Store emergency funds in high-yield savings accounts for easy access and some interest earnings (currently 4-5% APY). Online banks often offer better rates. Don't invest emergency funds in stocks—you need stability and immediate access."),
            ("How to Build an Emergency Fund Quickly", 
             "Set up automatic monthly transfers to savings. Use tax refunds, bonuses, or side hustle income. Cut one major expense (subscription, dining out) and redirect that money. Sell unused items. Start small—even $25/week adds up to $1,300 annually."),
        ])
        
        # 8. Insurance Types
        self.generate_qa_file("finance_insurance_types.md", "Types of Insurance", [
            ("What types of insurance do I need?", 
             "Essential: Health insurance (medical expenses), auto insurance (if you drive, legally required), renters/homeowners insurance (protect belongings/property), and life insurance (if others depend on your income). Consider: disability insurance (replaces income if injured), umbrella insurance (extra liability coverage)."),
            ("How much life insurance do I need?", 
             "A common rule: 10-12x your annual income. If you earn $50,000, get $500,000-$600,000 coverage. Term life insurance is affordable and sufficient for most people. Avoid whole life insurance unless you have specific estate planning needs—it's expensive with low returns."),
            ("What's the difference between term and whole life insurance?", 
             "Term life: Covers you for a specific period (10, 20, 30 years), affordable, no cash value. Best for most people. Whole life: Permanent coverage, expensive premiums, builds cash value slowly. Often pushed by salespeople due to high commissions."),
            ("Do I need disability insurance?", 
             "Yes, especially if you rely on your income to pay bills. Disability insurance replaces 50-70% of income if you can't work due to injury or illness. Many employers offer group coverage. If not, buy individual coverage—it's cheaper when you're young and healthy."),
        ])
        
        print(f"[FINANCE KB] Generated {len(list(self.output_dir.glob('*.md')))} files in {self.output_dir}")


def main():
    """Main entry point for generating finance KB."""
    generator = FinanceKBGenerator()
    generator.generate_all()
    print("[FINANCE KB] Finance knowledge base generation complete!")


if __name__ == "__main__":
    main()

