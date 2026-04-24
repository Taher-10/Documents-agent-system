CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- 1. Company
CREATE TABLE Company (
    Id UUID PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    CompanyGroupId UUID NOT NULL
);

-- 2. Site
CREATE TABLE Site (
    Id UUID PRIMARY KEY,
    Name VARCHAR(100) NOT NULL,
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 3. Employees (matches init1.sql)
CREATE TABLE Employees (
    Id UUID PRIMARY KEY,
    IsEnabled BOOLEAN NOT NULL DEFAULT TRUE,
    SerialNumber VARCHAR(20) NOT NULL,
    FirstName VARCHAR(100),
    LastName VARCHAR(100),
    FullName VARCHAR(200),
    Email VARCHAR(200),
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 4. Classifyings (matches init1.sql)
CREATE TABLE Classifyings (
    Id UUID PRIMARY KEY,
    Designation VARCHAR(200) NOT NULL,
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 5. Ini_Types (matches init1.sql)
CREATE TABLE Ini_Types (
    Id UUID PRIMARY KEY,
    Code VARCHAR(20) NOT NULL,
    Number INT NOT NULL DEFAULT 0,
    Designation VARCHAR(200) NOT NULL,
    Color VARCHAR(50) NULL,
    Source INT NOT NULL DEFAULT 0,
    DesSource VARCHAR(200) NULL,
    ImportType INT NOT NULL DEFAULT 0,
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 6. Ini_Domains (matches init1.sql)
CREATE TABLE Ini_Domains (
    Id UUID PRIMARY KEY,
    Code VARCHAR(20) NOT NULL,
    Number INT NOT NULL DEFAULT 0,
    Designation VARCHAR(200) NOT NULL,
    Color VARCHAR(50) NULL,
    Source INT NOT NULL DEFAULT 0,
    DesSource VARCHAR(200) NULL,
    ImportType INT NOT NULL DEFAULT 0,
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 7. Ini_SubDomains (referenced by FK in init1.sql)
CREATE TABLE Ini_SubDomains (
    Id UUID PRIMARY KEY,
    Code VARCHAR(20) NULL,
    Number INT NOT NULL DEFAULT 0,
    Designation VARCHAR(200) NOT NULL,
    DomainsId UUID NOT NULL REFERENCES Ini_Domains(Id),
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id)
);

-- 8. InternalDocs (matches init1.sql + extra fields needed by API)
CREATE TABLE InternalDocs (
    Id UUID PRIMARY KEY,
    EditionDate DATE NULL,
    Number INT NOT NULL DEFAULT 0,
    IsAutoCode BOOLEAN NOT NULL DEFAULT TRUE,
    IsAutoLifeCycle BOOLEAN NOT NULL DEFAULT FALSE,
    StartDate DATE NULL,
    DateWriting DATE NULL,
    DateChecking DATE NULL,
    DateApproval DATE NULL,
    DocumentParentId UUID NULL REFERENCES InternalDocs(Id),
    Code VARCHAR(50) NOT NULL DEFAULT '',
    "Index" VARCHAR(10) NOT NULL DEFAULT '00',
    ObjectDocument TEXT NULL,
    State SMALLINT NOT NULL DEFAULT 0,
    IsRecordingMedium BOOLEAN NOT NULL DEFAULT FALSE,
    Record_Classifying TEXT NULL,
    Record_AccessRight TEXT NULL,
    Record_Archiving TEXT NULL,
    Record_Destruction TEXT NULL,
    Record_PaperSupport BOOLEAN NOT NULL DEFAULT FALSE,
    Record_DigitalSupport BOOLEAN NOT NULL DEFAULT FALSE,
    ObjectModification TEXT NULL,
    DateDiffusion DATE NULL,
    DateApplication DATE NULL,
    ClassifyingId UUID NULL REFERENCES Classifyings(Id),
    Designation VARCHAR(500) NOT NULL,
    SiteId UUID NOT NULL REFERENCES Site(Id),
    CompanyId UUID NOT NULL REFERENCES Company(Id),
    Q BOOLEAN NOT NULL DEFAULT FALSE,
    S BOOLEAN NOT NULL DEFAULT FALSE,
    E BOOLEAN NOT NULL DEFAULT FALSE,
    H BOOLEAN NOT NULL DEFAULT FALSE,
    TypesId UUID NOT NULL REFERENCES Ini_Types(Id),
    DomainsId UUID NOT NULL REFERENCES Ini_Domains(Id),
    SubDomainId UUID NULL REFERENCES Ini_SubDomains(Id),
    VerificationByOrder BOOLEAN NOT NULL DEFAULT FALSE,
    ApprovalByOrder BOOLEAN NOT NULL DEFAULT FALSE,
    -- Extra fields not in init1.sql but needed for API simulation
    TypeContent INT NOT NULL DEFAULT 0,
    FilePath VARCHAR(1000) NULL,
    CreatedDate TIMESTAMP NOT NULL DEFAULT NOW(),
    CreatedBy UUID NULL REFERENCES Employees(Id),
    UpdatedDate TIMESTAMP NULL,
    UpdatedBy UUID NULL REFERENCES Employees(Id)
);

-- 9. InternalDocTeams (matches init1.sql field naming + extra fields for full API simulation)
CREATE TABLE InternalDocTeams (
    Id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    InternalDocumentId UUID NOT NULL REFERENCES InternalDocs(Id) ON DELETE CASCADE,
    EmployeeId UUID NOT NULL REFERENCES Employees(Id),
    Role_IsSupervisor BOOLEAN NOT NULL DEFAULT FALSE,
    Role_IsEditor BOOLEAN NOT NULL DEFAULT FALSE,
    Role_IsChecker BOOLEAN NOT NULL DEFAULT FALSE,
    Role_IsApprover BOOLEAN NOT NULL DEFAULT FALSE,
    Role_ToDistribute BOOLEAN NOT NULL DEFAULT FALSE,
    Role_IsClassifier BOOLEAN NOT NULL DEFAULT FALSE,
    Role_Comments TEXT NULL,
    Diffusion_IsAuomatic BOOLEAN NOT NULL DEFAULT FALSE,
    Diffusion_SentDate TIMESTAMP NULL,
    -- Extra fields for full workflow simulation
    CheckerOrder INT NOT NULL DEFAULT 0,
    ApproverOrder INT NOT NULL DEFAULT 0,
    DiffusionConsulted BOOLEAN NOT NULL DEFAULT FALSE,
    CreatedDate TIMESTAMP NOT NULL DEFAULT NOW(),
    CreatedBy UUID NULL REFERENCES Employees(Id),
    UpdatedDate TIMESTAMP NULL,
    UpdatedBy UUID NULL REFERENCES Employees(Id),
    CONSTRAINT uq_internaldocteams_document_employee UNIQUE (InternalDocumentId, EmployeeId)
);
