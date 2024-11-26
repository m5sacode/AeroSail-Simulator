import numpy as np
import matplotlib.pyplot as plt
from pyxfoil import Xfoil, set_workdir, set_xfoilexe
from scipy.interpolate import griddata

# Creates a Profile class to compute Cl Cd Cm coefficients to a manipulable profile started from a standard DAT file

def initializeXfoil(workdir, xfoilexe):
    set_workdir(workdir)
    set_xfoilexe(xfoilexe)

class Profile():
    def __init__(self, PlainDATfile):
        self.PlainDAT = np.genfromtxt(PlainDATfile, delimiter=' ')
        self.x = self.PlainDAT[:,0]
        self.y = self.PlainDAT[:,1]
        self.panels = None
        self.createXfoil_foil()
        self.flapdeflection = 0
        self.chordratio = 0.4
        self.cp = [] # Alpha, mach, re, results
        # print(self.PlainDAT)

    # Defines the number of panels used in simulations, set by defect to 160, the Xfoil standard
    def set_panels(self, panels):
        self.panels = panels

    # Adds a flap at the end of the profile with a certain chord ratio to the total chord and a deflection. It can save it to an optional target file
    # NOTE: If a flap is added and another flap is added over it then a double flap will be created unless reset foil is set to true
    def add_flap(self, chordratio, radiansdeflection, optionaltargetfile=None, reset_foil=False):
        # print(f"Initial deflection: {self.flapdeflection}, New deflection: {radiansdeflection}")

        # WARNING: THIS ONLY WORKS UP TO A DEFLECTION AROUND 30 DEGREES
        self.chordratio = chordratio
        if reset_foil:
            self.x = self.PlainDAT[:, 0]
            self.y = self.PlainDAT[:, 1]
            self.flapdeflection = radiansdeflection
            # print("Foil reset.")
        else:
            self.flapdeflection += radiansdeflection

        # print(f"Flap deflection after update: {self.flapdeflection}")

        self.flappedProfile = self.PlainDAT.copy()
        for i in range(np.size(self.x, axis=0)):
            rotatedpointx = (1 - chordratio) + (
                        np.cos(-self.flapdeflection) * (self.x[i] - (1 - chordratio)) - np.sin(-self.flapdeflection) *
                        self.y[i])
            rotatedpointy = (
                        np.sin(-self.flapdeflection) * (self.x[i] - (1 - chordratio)) + np.cos(-self.flapdeflection) *
                        self.y[i])

            if self.flappedProfile[i, 0] > (1 - chordratio):
                if self.flapdeflection > 0:
                    if rotatedpointy < self.y[i]:
                        self.flappedProfile[i, 0] = rotatedpointx
                        self.flappedProfile[i, 1] = rotatedpointy
                    elif self.flapdeflection > np.radians(36):
                        self.flappedProfile[i, 1] = -self.y[i]
                elif rotatedpointy > self.y[i]:
                    self.flappedProfile[i, 0] = rotatedpointx
                    self.flappedProfile[i, 1] = rotatedpointy
                elif self.flapdeflection < np.radians(-36):
                    self.flappedProfile[i, 1] = -self.y[i]

        if optionaltargetfile is not None:
            np.savetxt(optionaltargetfile, self.flappedProfile, fmt=['%.3f', '%.3f'])

        # Update xs and ys
        self.x = self.flappedProfile[:, 0]
        self.y = self.flappedProfile[:, 1]

        # Debugging: Print updated points
        # print(f"Updated flap profile: \n{self.flappedProfile}")

        return self.flappedProfile

    # Computes the coefficients for a certain condition. Saves them and returns them as [Cl, Cd, Cm]
    def get_coefficients(self, alpha, mach, re, errorstep = 0.1, errorange=2, interpolate=None):
        if interpolate is None:
            # Computes the coefficients, returns [Cl, Cd, Cm]
            self.createXfoil_foil()

            self.Cl , self.Cd, self.Cm = None, None, None
            polar = self.xfoil.run_polar(alpha, alpha+0.2, 0.2, mach=mach, re=re)
            if (len(polar.cd) != 0) and (len(polar.cl) != 0) and (len(polar.cm) != 0):  # Only if it does converge
                self.Cl = polar.cl[0]
                self.Cd = polar.cd[0]
                self.Cm = polar.cm[0]
            else: # Did not converge :( --> Try and linearly interpolate the value with values around it
                solvedleft = False
                alphat = alpha
                while(not solvedleft):
                    alphat -= errorstep
                    if alphat < alpha-errorange:
                        break
                    polar = self.xfoil.run_polar(alphat, alphat + 0.2, 0.2, mach=mach, re=re)
                    if (len(polar.cd) != 0) and (len(polar.cl) != 0) and (len(polar.cm) != 0):  # Only if it does converge
                        Clleft = polar.cl[0]
                        Cdleft = polar.cd[0]
                        Cmleft = polar.cm[0]
                        alphaleft = alphat
                        solvedleft = True
                if solvedleft:
                    alphat = alpha
                    solvedright = False
                    while alphat < alpha+errorange:
                        alphat += errorstep
                        polar = self.xfoil.run_polar(alphat, alphat + 0.2, 0.2, mach=mach, re=re)
                        if (len(polar.cd) != 0) and (len(polar.cl) != 0) and (len(polar.cm) != 0):  # Only if it does converge
                            Clright = polar.cl[0]
                            Cdright = polar.cd[0]
                            Cmright = polar.cm[0]
                            alpharight = alphat
                            solvedright = True
                if solvedright and solvedleft:
                    alphas = np.array([alphaleft, alpharight])
                    cls, cds, cms = np.array([Clleft, Clright]), np.array([Cdleft, Cdright]), np.array([Cmleft, Cmright])
                    self.Cl, self.Cd, self.Cm = np.interp(alpha, alphas, cls), np.interp(alpha, alphas, cds), np.interp(alpha, alphas, cms)
        else:
            self.load_interpolation(interpolate)
            Alphas, Flaps = np.meshgrid(self.interpalphas, self.interpflaps)
            points = np.vstack((Alphas.flatten(), Flaps.flatten())).T
            self.Cl = griddata(points, self.interpCl.flatten(), (alpha, self.flapdeflection), method='linear').item()
            self.Cd = griddata(points, self.interpCd.flatten(), (alpha, self.flapdeflection), method='linear').item()
            self.Cm = griddata(points, self.interpCloCd.flatten(), (alpha, self.flapdeflection), method='linear').item()
        return [self.Cl, self.Cd, self.Cm]

    # Plots the airfoil
    def plot_foil(self):
        self.createXfoil_foil()
        self.xfoil.plot_profile(ls='-')
        plt.show()

    # Plots and stores the Cp function of the profile
    def plot_cp(self, alpha, mach, re):
        rescase = self.xfoil.run_result(alpha, mach=mach, re=re)
        self.cp.append([alpha, mach, re, rescase])
        ax = None
        ax = rescase.plot_result(yaxis='cp', ax=ax, ls='-x')
        _ = ax.legend()
        plt.show()

    # Plotes a polar curve for two variables, 'alpha', 'cl', 'cd', 'clocd', 'cm'...
    def plot_curve(self, almin, almax, alint, mach, re, xaxis, yaxis):
        ax = None
        ax = self.xfoil.run_polar(almin, almax, alint, mach=mach, re=re).plot_polar(ax=ax, xaxis=xaxis, yaxis=yaxis, ls='-o')
        _ = ax.legend()
        plt.show()

    def create_interpolation(self, almin, almax, alint, flapmin, flapmaxs, flapint, mach, re, filename=None):
        self.interpflaps = np.arange(flapmin, flapmaxs, flapint)
        self.interpalphas = np.arange(almin, almax, alint)
        Alphas, Flaps = np.meshgrid(self.interpalphas, self.interpflaps)

        self.interpCl = np.zeros((len(self.interpalphas), len(self.interpflaps)))
        self.interpCd = np.zeros((len(self.interpalphas), len(self.interpflaps)))
        self.interpCloCd = np.zeros((len(self.interpalphas), len(self.interpflaps)))
        self.interpCm = np.zeros((len(self.interpalphas), len(self.interpflaps)))

        for j in range(len(self.interpflaps)):
            self.add_flap(self.chordratio, self.interpflaps[j], reset_foil=True)
            self.plot_foil()
            for i in range(len(self.interpalphas)):
                coefficients = self.get_coefficients(self.interpalphas[i], mach,re)
                self.interpCl[i, j] = coefficients[0]
                self.interpCd[i, j] = coefficients[1]
                self.interpCloCd[i, j] = coefficients[0]/coefficients[1]
                self.interpCm[i, j] = coefficients[2]


        if filename is not None:
            self.save_interpolation(filename)



    # Creates the PyXfoil object
    def createXfoil_foil(self):
        self.xfoil = Xfoil('Flapped E473')
        self.xfoil.set_points(self.x.tolist(), self.y.tolist())
        if self.panels is not None:
            self.xfoil.set_ppar(self.panels)
        else:
            self.xfoil.set_ppar(160)

    def save_interpolation(self, filename):
        np.savez(filename, interpalphas=self.interpalphas, interpflaps=self.interpflaps, interpCl=self.interpCl, interpCd=self.interpCd, interpCloCd=self.interpCloCd, interpCm=self.interpCm)

    # Loads the interpolation arrays from a npz file
    def load_interpolation(self, filename):
        npzfile = np.load(filename)
        self.interpalphas = npzfile['interpalphas']
        self.interpflaps = npzfile['interpflaps']
        self.interpCl = npzfile['interpCl']
        self.interpCd = npzfile['interpCd']
        self.interpCloCd = npzfile['interpCloCd']
        self.interpCm = npzfile['interpCm']


# TESTING CODE -------------------------------------------------

initializeXfoil('C:/Xfoil699src', 'C:/Xfoil699src/xfoil.exe')
testProfile = Profile('data/E473coordinates.txt')
testProfile.plot_foil()
testProfile.add_flap(0.4, np.radians(5), reset_foil=True)
testProfile.plot_foil()
testProfile.add_flap(0.4, np.radians(12), reset_foil=True)
testProfile.plot_foil()
# testProfile.plot_cp(5, 0, 1000000)
# testProfile.plot_curve(-10, 20, 0.5, 0, 1000000, 'alpha', 'cl')
# testProfile.create_interpolation(-10, 20, 1, np.radians(0), np.radians(20), np.radians(1), 0, 1000000, 'data/interp0.4profile')
print(testProfile.get_coefficients(10, 0, 1000000, interpolate='Data/interp0.4profile.npz'))