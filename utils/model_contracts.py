from pydantic import BaseModel
from typing import Literal, Optional, List

class WeatherData(BaseModel):
    latitude: float
    longitude: float
    temperature: float
    windspeed: float
    winddirection: float

class WeatherDataResponse(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    weatherData : WeatherData | None = None

class EmployeeMaster(BaseModel):
    employeeId:str
    name:str
    department:str
    location:str
    DOB:int
    isActive:bool
    email:str
    ssn:str
class EmployeeMasterResponseModel(BaseModel):
    dataFound: Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employee: EmployeeMaster = None

class EmployeeLeaveData(BaseModel):
    id:str
    employeeId:str
    name:str
    leaveType:str
    startDate:str
    endDate:str
    numberOfDays:int

class EmployeeLeaveResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    employeeLeave : EmployeeLeaveData | None = None

class RagData(BaseModel):
    score:Optional[float] = 0.0
    text:Optional[str] = ''
    title:Optional[str] = ''
class RagDataResponseModel(BaseModel):
    dataFound : Literal['FOUND', 'NOT FOUND', 'ERROR'] = 'NOT FOUND'
    results : List[RagData] = []

class InputDetails(BaseModel):
    inp_query:str

class UploadRequest(BaseModel):
    filename: str