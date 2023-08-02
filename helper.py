# General packages
import datetime
import pytz
import pandas as pd
import sys

# Python data class
from dataclasses import dataclass, field

# Refinitiv UI components
from refinitiv_widgets import ProgressBar

# Refinitiv Library
import refinitiv.data as rd
from refinitiv.data.content import historical_pricing

# Refinitiv UI
from dataclasses import dataclass, field
from refinitiv_widgets import DatetimePicker
from ipywidgets import Box


# Charting
import cufflinks as cf
cf.go_offline()

@dataclass
class DatePicker:
    """
    Provides a simple interface to select a series of dates/times to be used by the Intraday module.  The DatePicker is based on CodeBook widgets that provide a
    common UI experience to those available within Refinitiv Workspace.
    
    **Note:** The module presently defines a preset number of dates which can be changed within the modules' code.
    """
    # Constructor specifiers
    cnt: int = 5
    
    # Private properties
    _date_css: str = field(init=False, default='border: 2px solid green; width: 150px; border-radius: 20px', repr=False)
    _time_css: str = field(init=False, default='border: 2px solid green; width: 300px; border-radius: 20px', repr=False)
    _dates: list = field(init=False, default_factory=list, repr=False)
    _today: datetime.datetime = field(init=False, default=datetime.date.today(), repr=False)
    _time_range: DatetimePicker = field(init=False, repr=False)  
    
    # Post initialization
    def __post_init__(self) -> None:
        self.cnt = 5 if self.cnt < 1 or self.cnt > 10 else self.cnt
        
        # Initialize DatePicker instances
        delta = 1
        for i in range(self.cnt):
            # Inner loop to ignore weekends
            while True:
                d = self._today-datetime.timedelta(days=delta)
                if d.weekday() < 5:
                    break;
                delta += 1
                
            self._dates.append(DatetimePicker(css=self._date_css, value=[f'{d}'], weekdays_only=True))
            delta += 1
            
        # Initialize Time Picker instance
        value=["1900-01-01T09:30", "1900-01-01T16:00"]
        
        self._time_range = DatetimePicker(css=self._time_css,
                                          range_mode=True,
                                          duplex_mode="split",
                                          weekends_only=True, 
                                          timepicker_mode=True,
                                          value=value)
        
    # Capture date input
    def select_dates(self):
        """
        Display a collection of date objects.
        """
        print("Choose dates:")
        display(Box(children=self._dates))
        
    # Capture time input
    def select_times(self):
        """
        Display a simple date/time to/from interface.
        """
        print("\nOverride time range:")
        display(self._time_range)
    
    @property
    def dates(self):
        """
        Returns: The current date values.
        """
        return [datetime.datetime.strptime(x.value[0], "%Y-%m-%d") for x in self._dates]
    
    @property
    def time_range(self):
        """
        Returns: The current datetime values.
        """
        return [datetime.datetime.strptime(self._time_range.value[0], "%Y-%m-%dT%H:%M"),
                datetime.datetime.strptime(self._time_range.value[1], "%Y-%m-%dT%H:%M")]
    

@dataclass
class Intraday:
    """
    The module defines a single python data class responsible for the following:
    
    Defining the trading window
    ---------------------------
    The historical pricing interfaces accept and return measures based in GMT. To simplify usage of the interface, users typically prefer not to perform the mental 
    math of calculating offsets based on instruments that trade in different timezones.  Instead, we have performed the heavy lifting of the calculations by determining
    the timezone in which the instrument trades and calculating the proper times in order to capture the instruments' trading window.
    
    Generate intraday prices and volumes
    ------------------------------------
    For the selected dates passed in, the interface utilizes the historical pricing service to capture the minute bars for each trading day.  The measures calculated
    include the closing trading price within the bar as well as the volume traded within that bar.
    
    Calculate and capture measures
    ------------------------------
    The interface supports the ability to prepare the raw prices or to perform a net change calculation based on the first trade of the day.  The net change measure
    ('net'), or the net change percentage ('pct') provides the detection of movement throughout the trading window.  This movement acts as the basis of our 
    analysis to detect important trends.  in addition, we also capture the volumes for each trading bar.  Providing a measure of activity using the trading volume 
    provides invaluable insight into our analysis.
    
    Present our results
    -------------------
    Using the historical summaries and their associated measures, we provide the ability to present our results using popular graphing packages.  The presentation 
    outlines the distribution of our price measures along with the corresponding volumes.
    """
    _tz: str = field(init=False, repr=False)
    _label: str = field(init=False, repr=False)
    _prices: pd.DataFrame = field(init=False, repr=False)
    _volumes: pd.DataFrame = field(init=False, repr=False)
        
    def calculate_measures(self, ric, dates, time_range, measure=None):
        """Based on the specific instrument (RIC), for the specified dates, generate the price and volume measures used to evaluate the intraday activity for the
           specified trading window.  Refer to the 'Calculate and capture measure' section for details related to the 'measure' parameter.
        """         
        price = 'TRDPRC_1'
        volume = 'ACVOL_UNS'
        
        # Dates may be a single datetime instance
        if not isinstance(dates, list):
            dates = [dates]
        if len(dates) < 1 or len(time_range) != 2:
            return
    
        # Containers (prices/volumes)
        prices = []
        volumes = []
        self._prices = None
        self._volumes = None
    
        # Simple progress bar
        pb = ProgressBar(value=100, color="green")
        pb.value = 0
        display(pb)
        print("Processing...")
    
        # Retrieve timezone for our RIC
        if self.__get_timezone(ric):    
            # Iterate through out dates container, defining a time range and request for prices
            for date in dates:
                pb.value += 100/len(dates)   # Progress bar increment

                # Day to retrieve intraday values - define the local trading start/end hours
                start = datetime.datetime(date.year, date.month, date.day, time_range[0].hour, 
                                          time_range[0].minute, 0, tzinfo=pytz.timezone(self._tz))
                end = datetime.datetime(date.year, date.month, date.day, 
                                        time_range[1].hour, time_range[1].minute, 0, tzinfo=pytz.timezone(self._tz))

                # Convert to UTC as required by the historical pricing service
                start = start.astimezone(pytz.utc).replace(tzinfo=pytz.utc)
                end = end.astimezone(pytz.utc).replace(tzinfo=pytz.utc)

                try:               
                    # Retrieve our minute price bars for the specified day
                    response = historical_pricing.summaries.Definition(
                                        universe=ric, fields=[price, volume],
                                        interval=historical_pricing.Intervals.MINUTE,
                                        start=start, end=end).get_data()
                    df = response.data.df.dropna()
                    
                    if not df.empty:
                        # Mark the date index as UTC
                        df = df.tz_localize('UTC')

                        # Convert the date index for local time (for presentation)
                        index=df.index.tz_convert(self._tz)
                        df = df.set_index(index)

                        # Ensure our values our numeric (required for the measures calculation below)
                        df[price]=pd.to_numeric(df.iloc(1)[0])

                        # Derive the measure
                        if measure == 'net':
                            df[price] = df[price] - df[price][0]
                        elif measure == 'pct':
                            df[price] = (df[price] - df[price][0]) / df[price][0]

                        # Prepare the data for charting
                        price_df = df.drop([volume], axis=1)
                        volume_df = df.drop([price], axis=1)

                        price_df.rename(columns={price:df.index.max().date()},inplace=True)
                        price_df.index = price_df.index.time
                        volume_df.rename(columns={volume:df.index.max().date()},inplace=True)
                        volume_df.index = volume_df.index.time

                        prices.append(price_df)
                        volumes.append(volume_df)
                    else:
                        print(f'No data returned for RIC: {ric} for the range: {start}:{end}. Ignoring.')
                except Exception as e:
                    print(f"Issue retrieving data for RIC: {ric} for the range: {start}:{end}.  Ignoring\n\t{e}")             

        # Organize the results into a dataframe
        if (len(prices) > 0):
            self._prices = pd.concat(prices, axis=1, sort=False).dropna()
            self._volumes = pd.concat(volumes, axis=1, sort=False).dropna()
        else:
            print("Failed to generate any measures")
        print("**Done")
        return
      
    @property
    def prices(self):
        """After calculating the measures, the intraday prices for the selected days are generated.
           Returns: Pandas Dataframe representing the prices for each day generated
        """        
        return self._prices if hasattr(self, '_prices') else None
    
    @property
    def volumes(self):
        """After calculating the measures, the intraday trading volumes for the selected days are generated.
           Returns: Pandas Dataframe representing the volumes for each day generated
        """          
        return self._volumes if hasattr(self, '_volumes') else None
    
    @property
    def label(self):
        """A simple label representing the processed instrument.
        """
        return self._label
    
    def plot(self, title, theme='solar', dimensions=(1100,500)):
        """After calculating the measures, plot the prices and volume graphs defined within the trading window for the specified instrument.
        """         
        if self._prices is not None:
            if title is None:
                title = _label
            self.prices.iplot(theme=theme, title=title, dimensions=dimensions)
            self.volumes.iplot(theme=theme, kind='bar', barmode='stack', dimensions=dimensions)
        else:
            print("No measures generated")
    
    # Retrieve timezone for our RIC
    def __get_timezone(self, ric):
        success = False
        try:
            # The following code segment fails and will be addressed under ticket: EAPI-5733
            # A workaround is available below.
            #
            #df = rd.get_data(ric, ["TR.MASOperatingTZ", "CF_NAME"])
            #if not df.empty:
            #    self._tz = df.iat[0,1]
            #    self._label = f'{df.iat[0, 2]} (Timezone: {self._tz})'
            tz = rd.get_data(ric, ["TR.MASOperatingTZ"])
            nm = rd.get_data(ric, ["CF_NAME"])
            if not tz.empty:
                self._tz = tz.iat[0,1]
                self._label = f'{nm.iat[0,1]} (Timezone: {self._tz})'
                success = True
        except Exception as e:
            print(f"An exception occurred: {e}")
        finally:
            if not success:
                print(f"Failed to retrieve timezone information for: {ric}")
            return success
