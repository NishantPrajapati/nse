"""NSE trading calendar for identifying trading days and holidays."""

from datetime import date, datetime, timedelta
from typing import Optional

import pytz

from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class NSECalendar:
    """NSE trading calendar manager."""

    # NSE holidays for 2024 (update annually)
    # Source: https://www.nseindia.com/regulations/trading-holidays
    HOLIDAYS_2024 = [
        date(2024, 1, 26),  # Republic Day
        date(2024, 3, 8),   # Mahashivratri
        date(2024, 3, 25),  # Holi
        date(2024, 3, 29),  # Good Friday
        date(2024, 4, 11),  # Id-Ul-Fitr
        date(2024, 4, 17),  # Ram Navami
        date(2024, 4, 21),  # Mahavir Jayanti
        date(2024, 5, 1),   # Maharashtra Day
        date(2024, 6, 17),  # Bakri Id
        date(2024, 7, 17),  # Muharram
        date(2024, 8, 15),  # Independence Day
        date(2024, 9, 16),  # Ganesh Chaturthi
        date(2024, 10, 2),  # Mahatma Gandhi Jayanti
        date(2024, 10, 12), # Dussehra
        date(2024, 11, 1),  # Diwali Laxmi Pujan
        date(2024, 11, 15), # Gurunanak Jayanti
        date(2024, 12, 25), # Christmas
    ]

    # NSE holidays for 2025 (update annually)
    HOLIDAYS_2025 = [
        date(2025, 1, 26),  # Republic Day
        date(2025, 2, 26),  # Mahashivratri
        date(2025, 3, 14),  # Holi
        date(2025, 3, 31),  # Id-Ul-Fitr
        date(2025, 4, 10),  # Mahavir Jayanti
        date(2025, 4, 14),  # Dr. Ambedkar Jayanti
        date(2025, 4, 18),  # Good Friday
        date(2025, 5, 1),   # Maharashtra Day
        date(2025, 6, 7),   # Bakri Id
        date(2025, 8, 15),  # Independence Day
        date(2025, 8, 27),  # Ganesh Chaturthi
        date(2025, 10, 2),  # Mahatma Gandhi Jayanti
        date(2025, 10, 21), # Dussehra
        date(2025, 10, 20), # Diwali Laxmi Pujan
        date(2025, 11, 5),  # Gurunanak Jayanti
        date(2025, 12, 25), # Christmas
    ]

    # NSE holidays for 2026
    HOLIDAYS_2026 = [
        date(2026, 1, 26),  # Republic Day
        date(2026, 3, 3),   # Holi
        date(2026, 3, 21),  # Id-Ul-Fitr
        date(2026, 3, 30),  # Ram Navami
        date(2026, 4, 2),   # Mahavir Jayanti
        date(2026, 4, 3),   # Good Friday
        date(2026, 4, 6),   # Mahavir Jayanti
        date(2026, 4, 14),  # Dr. Ambedkar Jayanti
        date(2026, 5, 1),   # Maharashtra Day
        date(2026, 5, 28),  # Bakri Id
        date(2026, 8, 15),  # Independence Day
        date(2026, 9, 5),   # Ganesh Chaturthi
        date(2026, 10, 2),  # Mahatma Gandhi Jayanti
        date(2026, 10, 10), # Dussehra
        date(2026, 10, 27), # Diwali Laxmi Pujan
        date(2026, 11, 25), # Gurunanak Jayanti
        date(2026, 12, 25), # Christmas
    ]

    def __init__(self):
        """Initialize NSE calendar."""
        self.timezone = pytz.timezone(settings.scheduler_timezone)
        
        # Combine all holidays
        self.holidays = set(
            self.HOLIDAYS_2024 + self.HOLIDAYS_2025 + self.HOLIDAYS_2026
        )
        
        logger.info(
            "NSE calendar initialized",
            timezone=settings.scheduler_timezone,
            holidays_count=len(self.holidays),
        )

    def is_trading_day(self, check_date: Optional[date] = None) -> bool:
        """
        Check if a date is a trading day.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            True if trading day, False otherwise
        """
        if check_date is None:
            check_date = self.get_current_date()
        
        # Check if weekend
        if check_date.weekday() >= 5:  # Saturday=5, Sunday=6
            return False
        
        # Check if holiday
        if check_date in self.holidays:
            return False
        
        return True

    def get_current_date(self) -> date:
        """
        Get current date in IST.
        
        Returns:
            Current date in IST
        """
        now = datetime.now(self.timezone)
        return now.date()

    def get_current_datetime(self) -> datetime:
        """
        Get current datetime in IST, returned as naive UTC datetime for database compatibility.
        
        Returns:
            Current datetime in UTC (naive, no timezone info)
        """
        # Get current time in IST
        ist_time = datetime.now(self.timezone)
        # Convert to UTC and remove timezone info for database compatibility
        utc_time = ist_time.astimezone(pytz.UTC).replace(tzinfo=None)
        return utc_time

    def get_previous_trading_day(
        self,
        from_date: Optional[date] = None,
    ) -> date:
        """
        Get previous trading day.
        
        Args:
            from_date: Starting date (defaults to today)
            
        Returns:
            Previous trading day
        """
        if from_date is None:
            from_date = self.get_current_date()
        
        check_date = from_date - timedelta(days=1)
        
        while not self.is_trading_day(check_date):
            check_date -= timedelta(days=1)
        
        return check_date

    def get_next_trading_day(
        self,
        from_date: Optional[date] = None,
    ) -> date:
        """
        Get next trading day.
        
        Args:
            from_date: Starting date (defaults to today)
            
        Returns:
            Next trading day
        """
        if from_date is None:
            from_date = self.get_current_date()
        
        check_date = from_date + timedelta(days=1)
        
        while not self.is_trading_day(check_date):
            check_date += timedelta(days=1)
        
        return check_date

    def is_month_end_trading_day(
        self,
        check_date: Optional[date] = None,
    ) -> bool:
        """
        Check if date is the last trading day of the month.
        
        Args:
            check_date: Date to check (defaults to today)
            
        Returns:
            True if last trading day of month
        """
        if check_date is None:
            check_date = self.get_current_date()
        
        if not self.is_trading_day(check_date):
            return False
        
        # Check if next trading day is in a different month
        next_trading = self.get_next_trading_day(check_date)
        
        return next_trading.month != check_date.month

    def get_trading_days_in_month(
        self,
        year: int,
        month: int,
    ) -> list[date]:
        """
        Get all trading days in a month.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            List of trading days
        """
        # Get first and last day of month
        first_day = date(year, month, 1)
        
        if month == 12:
            last_day = date(year + 1, 1, 1) - timedelta(days=1)
        else:
            last_day = date(year, month + 1, 1) - timedelta(days=1)
        
        trading_days = []
        current = first_day
        
        while current <= last_day:
            if self.is_trading_day(current):
                trading_days.append(current)
            current += timedelta(days=1)
        
        return trading_days

    def get_last_trading_day_of_month(
        self,
        year: int,
        month: int,
    ) -> date:
        """
        Get last trading day of a month.
        
        Args:
            year: Year
            month: Month (1-12)
            
        Returns:
            Last trading day of month
        """
        trading_days = self.get_trading_days_in_month(year, month)
        
        if not trading_days:
            raise ValueError(f"No trading days in {year}-{month:02d}")
        
        return trading_days[-1]

    def add_holiday(self, holiday_date: date, name: Optional[str] = None) -> None:
        """
        Add a holiday to the calendar.
        
        Args:
            holiday_date: Holiday date
            name: Holiday name (optional)
        """
        self.holidays.add(holiday_date)
        logger.info(
            "Holiday added to calendar",
            date=holiday_date.isoformat(),
            name=name,
        )

    def remove_holiday(self, holiday_date: date) -> None:
        """
        Remove a holiday from the calendar.
        
        Args:
            holiday_date: Holiday date
        """
        if holiday_date in self.holidays:
            self.holidays.remove(holiday_date)
            logger.info("Holiday removed from calendar", date=holiday_date.isoformat())

    def get_market_hours(self) -> dict:
        """
        Get NSE market hours.
        
        Returns:
            Dictionary with market hours
        """
        return {
            "pre_open_start": "09:00",
            "pre_open_end": "09:15",
            "normal_start": "09:15",
            "normal_end": "15:30",
            "post_close_start": "15:40",
            "post_close_end": "16:00",
            "timezone": settings.scheduler_timezone,
        }

    def is_market_open(self, check_time: Optional[datetime] = None) -> bool:
        """
        Check if market is currently open.
        
        Args:
            check_time: Time to check (defaults to now)
            
        Returns:
            True if market is open
        """
        if check_time is None:
            check_time = self.get_current_datetime()
        
        # Check if trading day
        if not self.is_trading_day(check_time.date()):
            return False
        
        # Check time
        market_hours = self.get_market_hours()
        
        open_time = check_time.replace(hour=9, minute=15, second=0, microsecond=0)
        close_time = check_time.replace(hour=15, minute=30, second=0, microsecond=0)
        
        return open_time <= check_time <= close_time
